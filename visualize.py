#!/usr/bin/env python3
"""
Generate PNG/SVG topology and security diagrams from jericho-extractor output.

Usage:
    python visualize.py --account Portal-Prod
    python visualize.py --account Portal-Prod --output-dir output
    python visualize.py --account Portal-Prod --only security
    python visualize.py --account Portal-Prod --only vpc
    python visualize.py --account Portal-Prod --only graph
    python visualize.py --account Portal-Prod --only tgw
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


def load(account_dir: Path, name: str) -> list[dict]:
    path = account_dir / f"{name}.json"
    if not path.exists():
        logger.warning("File not found, skipping: %s", path)
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def generate(account_dir: Path, diagrams_dir: Path, only: str | None) -> None:
    from visualization import VPCDiagram, GraphVisualizer, SecurityVisualizer, TGWDiagram
    from topology.network_graph import NetworkGraph
    from topology.relationship_engine import RelationshipEngine

    diagrams_dir.mkdir(parents=True, exist_ok=True)

    # ── Load inventory ────────────────────────────────────────────────────────
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

    sg_analysis = load(account_dir, "relationships/security_groups_analysis")
    all_resources = [r for resources in inventory.values() for r in resources]

    # ── VPC topology diagram ──────────────────────────────────────────────────
    if only in (None, "vpc"):
        logger.info("Generating VPC topology diagram…")
        VPCDiagram().render(
            inventory,
            diagrams_dir / "vpc_topology.png",
            title="VPC Topology",
        )

    # ── Security exposure map ─────────────────────────────────────────────────
    if only in (None, "security"):
        if sg_analysis:
            logger.info("Generating security diagrams…")
            sec = SecurityVisualizer()
            sec.render_exposure_map(
                sg_analysis,
                diagrams_dir / "security_exposure.png",
                title="Security Group Exposure Map",
            )
            sec.render_summary_bar(
                sg_analysis,
                diagrams_dir / "security_posture.png",
                title="Security Posture Summary",
            )
            sec.render_public_resources(
                sg_analysis,
                all_resources,
                diagrams_dir / "public_resources.png",
                title="Publicly Exposed Resources",
            )
        else:
            logger.warning(
                "No security_groups_analysis.json found — run main.py first, then re-run visualize.py"
            )

    # ── Infrastructure dependency graph ───────────────────────────────────────
    if only in (None, "graph"):
        logger.info("Building networkx graph for visualization…")
        graph = NetworkGraph()
        graph.build_from_inventory(all_resources)
        edges = RelationshipEngine().build_all(inventory)
        graph.build_from_edges(edges)

        GraphVisualizer().render(
            graph,
            diagrams_dir / "dependency_graph.png",
            title="Infrastructure Dependency Graph",
        )

    # ── TGW topology ──────────────────────────────────────────────────────────
    if only in (None, "tgw"):
        logger.info("Generating TGW topology diagram…")
        TGWDiagram().render(
            inventory,
            diagrams_dir / "tgw_topology.png",
            title="Transit Gateway Topology",
        )

    print(f"\nDiagrams written to: {diagrams_dir}")
    for f in sorted(diagrams_dir.glob("*.png")):
        print(f"  {f.name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate PNG topology diagrams from jericho-extractor output"
    )
    parser.add_argument("--account",    required=True, help="Account folder name inside output/")
    parser.add_argument("--output-dir", default="output", help="Base output directory (default: output)")
    parser.add_argument(
        "--only",
        choices=["vpc", "security", "graph", "tgw"],
        default=None,
        help="Generate only one diagram type (default: all)",
    )
    args = parser.parse_args()

    account_dir  = Path(args.output_dir) / args.account
    diagrams_dir = account_dir / "diagrams"

    if not account_dir.exists():
        print(f"Error: directory not found: {account_dir}")
        raise SystemExit(1)

    generate(account_dir, diagrams_dir, args.only)


if __name__ == "__main__":
    main()
