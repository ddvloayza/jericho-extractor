from __future__ import annotations

"""Pure-Python HTML/SVG renderer — no numpy, no matplotlib, no C extensions."""

import json
import math
from pathlib import Path
from typing import Any


# ── Color palettes ────────────────────────────────────────────────────────────

RISK_COLORS = {
    "critical": "#D32F2F",
    "high":     "#F57C00",
    "medium":   "#FBC02D",
    "low":      "#388E3C",
    "info":     "#1565C0",
}

SUBNET_COLORS = {
    "public":   ("#E8F5E9", "#2E7D32"),
    "private":  ("#FFF9C4", "#F57F17"),
    "isolated": ("#FFEBEE", "#C62828"),
    "unknown":  ("#EEEEEE", "#9E9E9E"),
}

RESOURCE_COLORS = {
    "ec2":      "#FF8F00",
    "alb":      "#AD1457",
    "nlb":      "#880E4F",
    "nat":      "#00838F",
    "vpce":     "#4527A0",
    "eks":      "#F57F17",
    "default":  "#546E7A",
}


def _short(resource: dict, max_len: int = 26) -> str:
    name = resource.get("tags", {}).get("Name") or resource.get("resource_name") or resource.get("resource_id", "")
    return name if len(name) <= max_len else name[:max_len - 1] + "…"


# ── HTML skeleton ─────────────────────────────────────────────────────────────

def _html_page(title: str, body: str, extra_css: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:#0D1117;color:#E6EDF3;font-family:'Segoe UI',Arial,sans-serif;padding:20px}}
    h1{{font-size:1.4rem;margin-bottom:16px;color:#58A6FF}}
    h2{{font-size:1.1rem;margin:24px 0 10px;color:#79C0FF}}
    .badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:600;color:#fff}}
    .critical{{background:#D32F2F}} .high{{background:#F57C00}}
    .medium{{background:#FBC02D;color:#000}} .low{{background:#388E3C}}
    .info{{background:#1565C0}}
    table{{width:100%;border-collapse:collapse;font-size:.82rem;margin-bottom:24px}}
    th{{background:#161B22;color:#79C0FF;padding:8px 10px;text-align:left;border-bottom:1px solid #30363D}}
    td{{padding:7px 10px;border-bottom:1px solid #21262D;vertical-align:top}}
    tr:hover td{{background:#161B22}}
    .tag{{display:inline-block;background:#21262D;color:#8B949E;padding:1px 6px;border-radius:3px;
          font-size:.7rem;margin:1px}}
    {extra_css}
  </style>
</head>
<body>
<h1>{title}</h1>
{body}
</body>
</html>"""


# ── Security report ───────────────────────────────────────────────────────────

def render_security_report(
    sg_analyses: list[dict[str, Any]],
    output_path: Path,
    account_name: str = "",
) -> None:
    risk_order = ["critical", "high", "medium", "low", "info"]
    sorted_sgs = sorted(
        sg_analyses,
        key=lambda a: (risk_order.index(str(a.get("overall_risk", "info"))) if str(a.get("overall_risk", "info")) in risk_order else 99,
                       -a.get("attached_count", 0)),
    )

    # Summary cards
    counts = {r: sum(1 for a in sg_analyses if str(a.get("overall_risk")) == r) for r in risk_order}
    cards_html = '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px">'
    for risk in risk_order:
        color = RISK_COLORS.get(risk, "#546E7A")
        cards_html += (
            f'<div style="background:{color}22;border:1px solid {color};border-radius:8px;'
            f'padding:12px 20px;min-width:110px;text-align:center">'
            f'<div style="font-size:1.8rem;font-weight:700;color:{color}">{counts[risk]}</div>'
            f'<div style="font-size:.8rem;color:#8B949E;text-transform:uppercase">{risk}</div>'
            f'</div>'
        )
    cards_html += "</div>"

    # SG table
    rows = ""
    for sg in sorted_sgs:
        risk     = str(sg.get("overall_risk", "info"))
        color    = RISK_COLORS.get(risk, "#546E7A")
        flags    = sg.get("exposure_flags", [])
        flags_html = "".join(f'<span class="tag" style="background:{color}33;color:{color}">{f}</span>' for f in flags)
        attached = "<br>".join(sg.get("attached_resources", [])[:5])
        if sg.get("attached_count", 0) > 5:
            attached += f'<br><span style="color:#8B949E">+{sg["attached_count"]-5} more</span>'

        inbound_summary = _rules_summary(sg.get("inbound_analysis", []))
        outbound_summary = _rules_summary(sg.get("outbound_analysis", []))

        rows += f"""<tr>
          <td><code style="color:#58A6FF">{sg.get('security_group_id','')}</code><br>
              <span style="color:#8B949E;font-size:.75rem">{sg.get('security_group_name','')}</span></td>
          <td><span class="badge {risk}">{risk.upper()}</span></td>
          <td>{flags_html}</td>
          <td style="font-size:.75rem;color:#8B949E">{attached or '—'}</td>
          <td style="font-size:.75rem">{inbound_summary}</td>
          <td style="font-size:.75rem">{outbound_summary}</td>
        </tr>"""

    table = f"""<table>
      <thead><tr>
        <th>Security Group</th><th>Risk</th><th>Exposure Flags</th>
        <th>Attached Resources</th><th>Inbound</th><th>Outbound</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>"""

    body = cards_html + f"<h2>Security Groups ({len(sg_analyses)})</h2>" + table
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_html_page(f"Security Report — {account_name}", body), encoding="utf-8")


def _rules_summary(rules: list[dict]) -> str:
    lines = []
    for r in rules[:6]:
        proto = r.get("protocol", "-1")
        fp    = r.get("from_port")
        tp    = r.get("to_port")
        cidrs = ", ".join((r.get("cidrs") or [])[:2])
        tags  = r.get("risk_tags", [])
        risk  = str(r.get("risk_level", "info"))
        color = RISK_COLORS.get(risk, "#546E7A")
        port_str = f"{fp}–{tp}" if fp is not None and fp != tp else (str(fp) if fp is not None else "all")
        tag_str  = " ".join(f'<span style="color:{color};font-size:.65rem">{t}</span>' for t in tags)
        lines.append(f"{proto}/{port_str} {cidrs} {tag_str}")
    if len(rules) > 6:
        lines.append(f'<span style="color:#8B949E">+{len(rules)-6} more</span>')
    return "<br>".join(lines) or "—"


# ── VPC topology report ───────────────────────────────────────────────────────

def render_vpc_report(
    inventory: dict[str, list[dict[str, Any]]],
    output_path: Path,
    account_name: str = "",
) -> None:
    vpcs    = inventory.get("vpcs", [])
    subnets = inventory.get("subnets", [])
    ec2     = [i for i in inventory.get("ec2", []) if i.get("state") != "terminated"]
    lbs     = inventory.get("load_balancers", [])
    nats    = inventory.get("nat_gateways", [])
    igws    = inventory.get("internet_gateways", [])
    eps     = inventory.get("vpc_endpoints", [])
    eks_res = inventory.get("eks", [])

    # Indexes
    subs_by_vpc: dict[str, list[dict]] = {}
    for s in subnets:
        subs_by_vpc.setdefault(s.get("vpc_id", ""), []).append(s)

    ec2_by_sub: dict[str, list[dict]] = {}
    for i in ec2:
        ec2_by_sub.setdefault(i.get("subnet_id", ""), []).append(i)

    lb_by_sub: dict[str, list[dict]] = {}
    for lb in lbs:
        for az in lb.get("availability_zones", []):
            lb_by_sub.setdefault(az.get("SubnetId", ""), []).append(lb)

    nat_by_sub: dict[str, list[dict]] = {}
    for nat in nats:
        nat_by_sub.setdefault(nat.get("subnet_id", ""), []).append(nat)

    ep_by_sub: dict[str, list[dict]] = {}
    for ep in eps:
        for sid in ep.get("associated_subnet_ids", []):
            ep_by_sub.setdefault(sid, []).append(ep)

    igw_by_vpc: dict[str, list[dict]] = {}
    for igw in igws:
        for vid in igw.get("attached_vpc_ids", []):
            igw_by_vpc.setdefault(vid, []).append(igw)

    eks_by_vpc: dict[str, list[dict]] = {}
    for cl in eks_res:
        if cl.get("resource_type") == "aws::eks::cluster":
            eks_by_vpc.setdefault(cl.get("vpc_id", ""), []).append(cl)

    body = ""
    for vpc in vpcs:
        vid      = vpc["resource_id"]
        vname    = _short(vpc, 40)
        vcidr    = vpc.get("cidr_block", "")
        vpc_subs = subs_by_vpc.get(vid, [])
        n_igws   = len(igw_by_vpc.get(vid, []))
        n_eks    = len(eks_by_vpc.get(vid, []))

        # AZ grouping
        az_map: dict[str, list[dict]] = {}
        for s in vpc_subs:
            az_map.setdefault(s.get("availability_zone", "?"), []).append(s)

        body += f"""
<div style="border:2px solid #1565C0;border-radius:10px;padding:16px;margin-bottom:28px;background:#0D1B2A">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
    <span style="font-size:1rem;font-weight:700;color:#58A6FF">{vname}</span>
    <code style="color:#8B949E;font-size:.8rem">{vid}</code>
    <span style="color:#79C0FF;font-size:.85rem">{vcidr}</span>
    {"<span class='badge' style='background:#6A1B9A'>IGW</span>" * n_igws}
    {"<span class='badge' style='background:#F57F17'>EKS</span>" * n_eks}
  </div>
  <div style="display:flex;gap:12px;flex-wrap:wrap">"""

        type_order = {"public": 0, "private": 1, "isolated": 2, "unknown": 3}
        for az_name in sorted(az_map.keys()):
            az_subs = sorted(az_map[az_name], key=lambda s: type_order.get(s.get("subnet_type", "unknown"), 3))
            body += f'<div style="flex:1;min-width:220px"><div style="color:#79C0FF;font-size:.75rem;margin-bottom:6px">AZ: {az_name}</div>'
            for sub in az_subs:
                sid    = sub["resource_id"]
                stype  = sub.get("subnet_type", "unknown")
                sname  = _short(sub, 28)
                scidr  = sub.get("cidr_block", "")
                sfill, sstroke = SUBNET_COLORS.get(stype, SUBNET_COLORS["unknown"])

                resources_html = _subnet_resources(
                    sid, ec2_by_sub, lb_by_sub, nat_by_sub, ep_by_sub
                )

                body += f"""
  <div style="border:1px solid {sstroke};border-radius:6px;background:{sfill}CC;padding:8px;margin-bottom:8px">
    <div style="font-weight:600;font-size:.78rem;color:#333;margin-bottom:4px">{sname}</div>
    <div style="font-size:.72rem;color:#555;margin-bottom:6px">{scidr} · <em>{stype}</em></div>
    {resources_html}
  </div>"""
            body += "</div>"

        body += "</div></div>"

    # Summary table
    summary_rows = "".join(
        f"<tr><td>{_short(v,40)}</td><td><code>{v['resource_id']}</code></td>"
        f"<td>{v.get('cidr_block','')}</td>"
        f"<td>{len(subs_by_vpc.get(v['resource_id'],[]))}</td>"
        f"<td>{sum(len(ec2_by_sub.get(s['resource_id'],[]))for s in subs_by_vpc.get(v['resource_id'],[]))}</td>"
        f"<td>{'✅' if igw_by_vpc.get(v['resource_id']) else '—'}</td></tr>"
        for v in vpcs
    )
    summary = f"""<h2>VPC Summary</h2>
    <table><thead><tr>
      <th>Name</th><th>VPC ID</th><th>CIDR</th><th>Subnets</th><th>EC2</th><th>IGW</th>
    </tr></thead><tbody>{summary_rows}</tbody></table>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_html_page(f"VPC Topology — {account_name}", summary + body), encoding="utf-8")


def _subnet_resources(sid, ec2_by_sub, lb_by_sub, nat_by_sub, ep_by_sub) -> str:
    items = []
    for inst in ec2_by_sub.get(sid, []):
        items.append(f'<span class="tag" style="background:#FF8F0033;color:#FF8F00">EC2 {_short(inst,16)}</span>')
    for lb in lb_by_sub.get(sid, []):
        items.append(f'<span class="tag" style="background:#AD145733;color:#AD1457">LB {_short(lb,16)}</span>')
    for nat in nat_by_sub.get(sid, []):
        items.append(f'<span class="tag" style="background:#00838F33;color:#00838F">NAT {_short(nat,12)}</span>')
    for ep in ep_by_sub.get(sid, []):
        svc = ep.get("service_name", "").split(".")[-1]
        items.append(f'<span class="tag" style="background:#4527A033;color:#9C77E0">EP {svc[:12]}</span>')
    return "".join(items) or '<span style="color:#aaa;font-size:.7rem">empty</span>'


# ── Graph summary report ──────────────────────────────────────────────────────

def render_graph_report(
    graph_summary: dict[str, Any],
    internet_facing: list[dict[str, Any]],
    nat_dependents: list[dict[str, Any]],
    output_path: Path,
    account_name: str = "",
) -> None:
    def stat_card(label: str, value: Any, color: str = "#58A6FF") -> str:
        return (
            f'<div style="background:#161B22;border:1px solid #30363D;border-radius:8px;'
            f'padding:14px 20px;min-width:140px;text-align:center">'
            f'<div style="font-size:1.6rem;font-weight:700;color:{color}">{value}</div>'
            f'<div style="font-size:.78rem;color:#8B949E">{label}</div></div>'
        )

    cards = '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px">'
    cards += stat_card("Nodes",             graph_summary.get("node_count", 0))
    cards += stat_card("Edges",             graph_summary.get("edge_count", 0))
    cards += stat_card("Internet-Facing",   graph_summary.get("internet_facing_count", 0), "#D32F2F")
    cards += stat_card("Public Subnets",    graph_summary.get("public_subnet_count", 0),   "#2E7D32")
    cards += stat_card("Private Subnets",   graph_summary.get("private_subnet_count", 0),  "#F57F17")
    cards += stat_card("Components",        graph_summary.get("connected_components", 0))
    cards += "</div>"

    def resource_table(resources: list[dict], heading: str, color: str) -> str:
        if not resources:
            return f"<h2>{heading}</h2><p style='color:#8B949E'>None found.</p>"
        rows = "".join(
            f"<tr><td><code>{r.get('resource_id','')}</code></td>"
            f"<td>{r.get('resource_type','').split('::')[-1]}</td>"
            f"<td>{r.get('tags',{}).get('Name') or r.get('resource_name','')}</td>"
            f"<td>{r.get('region','')}</td></tr>"
            for r in resources[:100]
        )
        return (
            f'<h2 style="color:{color}">{heading} ({len(resources)})</h2>'
            f'<table><thead><tr><th>ID</th><th>Type</th><th>Name</th><th>Region</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
        )

    body = (
        cards
        + resource_table(internet_facing, "Internet-Facing Resources", "#D32F2F")
        + resource_table(nat_dependents,  "Resources Behind NAT",      "#F57C00")
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_html_page(f"Graph Analysis — {account_name}", body), encoding="utf-8")
