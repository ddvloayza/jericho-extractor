#!/usr/bin/env python3
"""
Generate topology and security diagrams from jericho-extractor output.

Tries matplotlib (PNG) first; falls back to pure-Python HTML reports
when matplotlib/numpy are unavailable (e.g. blocked by App Control).

Usage:
    python visualize.py --account Portal-Prod
    python visualize.py --account Portal-Prod --output-dir output
    python visualize.py --account Portal-Prod --only security
    python visualize.py --account Portal-Prod --only vpc
    python visualize.py --account Portal-Prod --only graph
    python visualize.py --account Portal-Prod --only tgw
    python visualize.py --account Portal-Prod --format html
    python visualize.py --account Portal-Prod --format png
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Detect matplotlib availability upfront
try:
    import matplotlib  # noqa: F401
    _MPL_OK = True
except Exception:
    _MPL_OK = False


def load(account_dir: Path, name: str) -> list[dict]:
    path = account_dir / f"{name}.json"
    if not path.exists():
        logger.warning("File not found, skipping: %s", path)
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def generate(account_dir: Path, diagrams_dir: Path, only: str | None, fmt: str) -> None:
    diagrams_dir.mkdir(parents=True, exist_ok=True)

    use_html = (fmt == "html") or (fmt == "auto" and not _MPL_OK)
    if use_html and fmt == "auto":
        logger.info("matplotlib unavailable — generating HTML reports instead of PNG")

    # ── Load data ─────────────────────────────────────────────────────────────
    inventory = {
        "vpcs":                        load(account_dir, "vpcs"),
        "subnets":                     load(account_dir, "subnets"),
        "ec2":                         load(account_dir, "ec2"),
        "load_balancers":              load(account_dir, "load_balancers"),
        "nat_gateways":                load(account_dir, "nat_gateways"),
        "internet_gateways":           load(account_dir, "internet_gateways"),
        "vpc_endpoints":               load(account_dir, "vpc_endpoints"),
        "eks":                         load(account_dir, "eks"),
        "transit_gateways":            load(account_dir, "transit_gateways"),
        "transit_gateway_attachments": load(account_dir, "transit_gateway_attachments"),
        "security_groups":             load(account_dir, "security_groups"),
        "network_interfaces":          load(account_dir, "network_interfaces"),
        "route_tables":                load(account_dir, "route_tables"),
        "target_groups":               load(account_dir, "target_groups"),
        "vpc_peerings":                load(account_dir, "vpc_peerings"),
    }

    sg_analysis  = load(account_dir, "relationships/security_groups_analysis")
    all_resources = [r for resources in inventory.values() for r in resources]
    account_name  = account_dir.name

    # ── VPC ───────────────────────────────────────────────────────────────────
    if only in (None, "vpc"):
        if use_html:
            from visualization.html_renderer import render_vpc_report
            out = diagrams_dir / "vpc_topology.html"
            render_vpc_report(inventory, out, account_name)
            logger.info("VPC topology report -> %s", out)
        else:
            from visualization.vpc_diagram import VPCDiagram
            VPCDiagram().render(inventory, diagrams_dir / "vpc_topology.png", title="VPC Topology")

    # ── Security ──────────────────────────────────────────────────────────────
    if only in (None, "security"):
        if not sg_analysis:
            logger.warning("No security_groups_analysis.json — run main.py first")
        elif use_html:
            from visualization.html_renderer import render_security_report
            out = diagrams_dir / "security_report.html"
            render_security_report(sg_analysis, out, account_name)
            logger.info("Security report -> %s", out)
        else:
            from visualization.security_visualizer import SecurityVisualizer
            sec = SecurityVisualizer()
            sec.render_exposure_map(sg_analysis, diagrams_dir / "security_exposure.png")
            sec.render_summary_bar(sg_analysis, diagrams_dir / "security_posture.png")
            sec.render_public_resources(sg_analysis, all_resources, diagrams_dir / "public_resources.png")

    # ── Graph ─────────────────────────────────────────────────────────────────
    if only in (None, "graph"):
        from topology.network_graph import NetworkGraph
        from topology.relationship_engine import RelationshipEngine

        logger.info("Building network graph…")
        graph = NetworkGraph()
        graph.build_from_inventory(all_resources)
        graph.build_from_edges(RelationshipEngine().build_all(inventory))

        if use_html:
            from visualization.html_renderer import render_graph_report
            out = diagrams_dir / "graph_analysis.html"
            render_graph_report(
                graph.summary(),
                graph.get_internet_facing(),
                graph.get_nat_dependents(),
                out,
                account_name,
            )
            logger.info("Graph analysis report -> %s", out)
        else:
            from visualization.graph_visualizer import GraphVisualizer
            GraphVisualizer().render(graph, diagrams_dir / "dependency_graph.png")

    # ── Hierarchy ─────────────────────────────────────────────────────────────
    if only in (None, "hierarchy"):
        if use_html:
            from visualization.html_renderer import render_hierarchy_report
            out = diagrams_dir / "network_hierarchy.html"
            render_hierarchy_report(inventory, sg_analysis, out, account_name)
            logger.info("Network hierarchy -> %s", out)

    # ── TGW ───────────────────────────────────────────────────────────────────
    if only in (None, "tgw"):
        if use_html:
            # TGW as a simple HTML table
            _render_tgw_html(inventory, diagrams_dir / "tgw_topology.html", account_name)
        else:
            from visualization.tgw_diagram import TGWDiagram
            TGWDiagram().render(inventory, diagrams_dir / "tgw_topology.png")

    # ── Print summary ─────────────────────────────────────────────────────────
    ext = "html" if use_html else "png"
    print(f"\nDiagrams written to: {diagrams_dir}")
    for f in sorted(diagrams_dir.glob(f"*.{ext}")):
        print(f"  {f.name}")


def _render_tgw_html(inventory: dict, output_path: Path, account_name: str) -> None:
    from visualization.html_renderer import _html_page, _chip
    tgws   = inventory.get("transit_gateways", [])
    atts   = inventory.get("transit_gateway_attachments", [])
    vpcs   = {v["resource_id"]: v for v in inventory.get("vpcs", [])}

    if not tgws and not atts:
        logger.info("No TGW resources found")
        return

    att_by_tgw: dict[str, list] = {}
    for a in atts:
        att_by_tgw.setdefault(a.get("transit_gateway_id", "?"), []).append(a)

    rows = ""
    for tgw_id, tgw_atts in att_by_tgw.items():
        for att in tgw_atts:
            vpc_id   = att.get("resource_id_ref", "")
            vpc      = vpcs.get(vpc_id, {})
            vpc_name = vpc.get("tags", {}).get("Name") or vpc_id
            state    = att.get("state", "")
            state_chip = _chip(
                state.upper(),
                "#EEFBF1" if state == "available" else "#FFF7EE",
                "#1F7A35" if state == "available" else "#B86200",
            )
            rows += (
                f"<tr>"
                f"<td><code>{tgw_id}</code></td>"
                f"<td><code>{att['resource_id']}</code></td>"
                f"<td>{att.get('attachment_type','')}</td>"
                f"<td><code>{vpc_id}</code></td>"
                f"<td>{vpc_name}</td>"
                f"<td><code>{vpc.get('cidr_block','')}</code></td>"
                f"<td>{state_chip}</td>"
                f"</tr>"
            )

    n_tgws = len(tgws)
    n_atts = len(atts)
    hero_stats = [
        {"label": "Transit Gateways", "value": n_tgws},
        {"label": "Attachments",      "value": n_atts},
        {"label": "VPCs Attached",    "value": len({a.get("resource_id_ref","") for a in atts if a.get("resource_id_ref")})},
    ]

    no_row = '<tr><td colspan="7" style="color:var(--ig2)">No TGW attachments found</td></tr>'
    body = (
        '<div class="sec-eyebrow">Network Connectivity</div>'
        f'<div class="sec-title">Transit Gateway Topology &middot; <strong>{account_name}</strong></div>'
        f'<div class="sec-intro">{n_tgws} transit gateway(s) with {n_atts} VPC attachment(s).</div>'
        '<div class="twrap"><table>'
        "<thead><tr>"
        "<th>TGW ID</th><th>Attachment ID</th><th>Type</th>"
        "<th>VPC ID</th><th>VPC Name</th><th>CIDR</th><th>State</th>"
        "</tr></thead>"
        f"<tbody>{rows or no_row}</tbody>"
        "</table></div>"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _html_page(
            title=f"TGW Topology — {account_name}",
            body=body,
            account_name=account_name,
            hero_stats=hero_stats,
            hero_title=f"Transit Gateway &middot; <strong>{account_name}</strong>",
            hero_sub=f"{n_tgws} Transit Gateway(s) connecting {n_atts} VPC attachment(s).",
            hero_eyebrow=f"Network Connectivity &middot; {account_name}",
        ),
        encoding="utf-8",
    )
    logger.info("TGW topology report -> %s", output_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate topology diagrams from jericho-extractor output"
    )
    parser.add_argument("--account",    required=True, help="Account folder name inside output/")
    parser.add_argument("--output-dir", default="output", help="Base output directory (default: output)")
    parser.add_argument(
        "--only",
        choices=["vpc", "security", "graph", "tgw", "hierarchy"],
        default=None,
        help="Generate only one diagram type (default: all)",
    )
    parser.add_argument(
        "--format",
        choices=["auto", "html", "png"],
        default="auto",
        help="Output format: auto (html if matplotlib unavailable), html, or png (default: auto)",
    )
    args = parser.parse_args()

    account_dir  = Path(args.output_dir) / args.account
    diagrams_dir = account_dir / "diagrams"

    if not account_dir.exists():
        print(f"Error: directory not found: {account_dir}")
        raise SystemExit(1)

    generate(account_dir, diagrams_dir, args.only, args.format)


if __name__ == "__main__":
    main()
