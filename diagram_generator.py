#!/usr/bin/env python3
"""
Generate a draw.io network diagram from jericho-extractor output.

Usage:
    python diagram_generator.py --account Portal-Prod
    python diagram_generator.py --account Portal-Prod --output-dir output
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString


# ── Layout constants ──────────────────────────────────────────────────────────
CANVAS_MARGIN     = 80
VPC_PADDING       = 60
VPC_GAP           = 120
SUBNET_W          = 300
SUBNET_GAP        = 20
RESOURCE_W        = 56
RESOURCE_H        = 56
RESOURCE_LABEL_H  = 18
RESOURCE_MARGIN   = 14
RESOURCES_PER_ROW = 3
SUBNET_H_MIN      = 130
GATEWAY_SIZE      = 56
GATEWAY_MARGIN    = 50
AZ_LABEL_H        = 30
INTERNET_SIZE     = 60
INTERNET_Y        = 20


# ── AWS draw.io styles ────────────────────────────────────────────────────────
def _icon(res_icon: str, fill: str) -> str:
    return (
        f"outlineConnect=0;fontColor=#232F3E;gradientColor=none;strokeColor=none;"
        f"fillColor={fill};labelBackgroundColor=#ffffff;align=center;html=1;"
        f"fontSize=11;fontStyle=0;aspect=fixed;"
        f"shape=mxgraph.aws4.resourceIcon;resIcon={res_icon};"
    )


def _group(gr_icon: str, fill: str, stroke: str, font_size: int = 11) -> str:
    return (
        f"points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],"
        f"[1,1],[0.75,1],[0.5,1],[0.25,1],[0,1],[0,0.75],[0,0.5],[0,0.25]];"
        f"shape=mxgraph.aws4.group;grIcon={gr_icon};"
        f"verticalLabelPosition=top;verticalAlign=bottom;"
        f"fillColor={fill};strokeColor={stroke};fontSize={font_size};fontStyle=1;"
        f"spacingTop=5;"
    )


STYLES: dict[str, str] = {
    "vpc":             _group("mxgraph.aws4.group_vpc",             "#E6F3FF", "#147EBA", 13),
    "subnet_public":   _group("mxgraph.aws4.group_public_subnet",   "#E8F5E9", "#2E7D32"),
    "subnet_private":  _group("mxgraph.aws4.group_private_subnet",  "#FFF9C4", "#F57F17"),
    "subnet_isolated": _group("mxgraph.aws4.group_private_subnet",  "#FFEBEE", "#C62828"),
    "subnet_unknown":  _group("mxgraph.aws4.group_private_subnet",  "#F5F5F5", "#9E9E9E"),
    "igw":   _icon("mxgraph.aws4.internet_gateway",          "#8C4FFF"),
    "nat":   _icon("mxgraph.aws4.nat_gateway",               "#8C4FFF"),
    "tgw":   _icon("mxgraph.aws4.transit_gateway",           "#8C4FFF"),
    "vpce":  _icon("mxgraph.aws4.vpc_endpoints",             "#8C4FFF"),
    "ec2":   _icon("mxgraph.aws4.ec2",                       "#ED7100"),
    "alb":   _icon("mxgraph.aws4.application_load_balancer", "#E7157B"),
    "nlb":   _icon("mxgraph.aws4.network_load_balancer",     "#E7157B"),
    "internet": (
        "shape=mxgraph.aws4.internet_alt2;fillColor=#232F3E;strokeColor=none;"
        "fontColor=#232F3E;gradientColor=none;labelBackgroundColor=#ffffff;"
        "align=center;html=1;fontSize=12;fontStyle=1;aspect=fixed;"
    ),
    "edge": (
        "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;"
        "jettySize=auto;exitX=0.5;exitY=0;exitDx=0;exitDy=0;"
        "entryX=0.5;entryY=1;entryDx=0;entryDy=0;"
    ),
    "edge_dashed": (
        "edgeStyle=orthogonalEdgeStyle;rounded=1;dashed=1;dashPattern=8 4;"
        "strokeColor=#999999;exitX=0.5;exitY=0;exitDx=0;exitDy=0;"
        "entryX=0.5;entryY=1;entryDx=0;entryDy=0;"
    ),
}


# ── XML builder ───────────────────────────────────────────────────────────────
class DrawioBuilder:
    def __init__(self) -> None:
        self._counter = 10
        self._id_map: dict[str, str] = {}
        self._cells: list[Element] = []

    def _next_id(self) -> str:
        cid = str(self._counter)
        self._counter += 1
        return cid

    def _cell_id(self, resource_id: str) -> str:
        if resource_id not in self._id_map:
            self._id_map[resource_id] = self._next_id()
        return self._id_map[resource_id]

    def add_vertex(
        self,
        resource_id: str,
        label: str,
        style: str,
        x: float,
        y: float,
        w: float,
        h: float,
        parent: str = "1",
    ) -> str:
        cid = self._cell_id(resource_id)
        cell = Element("mxCell", {
            "id": cid,
            "value": label,
            "style": style,
            "vertex": "1",
            "parent": self._id_map.get(parent, parent),
        })
        SubElement(cell, "mxGeometry", {
            "x": str(round(x)),
            "y": str(round(y)),
            "width": str(round(w)),
            "height": str(round(h)),
            "as": "geometry",
        })
        self._cells.append(cell)
        return cid

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        label: str = "",
        style: str | None = None,
        parent: str = "1",
    ) -> None:
        src = self._id_map.get(source_id)
        tgt = self._id_map.get(target_id)
        if not src or not tgt:
            return
        eid = self._next_id()
        cell = Element("mxCell", {
            "id": eid,
            "value": label,
            "style": style or STYLES["edge"],
            "edge": "1",
            "source": src,
            "target": tgt,
            "parent": self._id_map.get(parent, parent),
        })
        SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
        self._cells.append(cell)

    def to_xml(self) -> str:
        mxfile = Element("mxfile", {"host": "jericho-extractor"})
        diagram = SubElement(mxfile, "diagram", {"name": "Network Topology"})
        model = SubElement(diagram, "mxGraphModel", {
            "dx": "1422", "dy": "762", "grid": "1", "gridSize": "10",
            "guides": "1", "tooltips": "1", "connect": "1", "arrows": "1",
            "fold": "1", "page": "1", "pageScale": "1",
            "pageWidth": "3300", "pageHeight": "2338",
            "math": "0", "shadow": "0",
        })
        root = SubElement(model, "root")
        SubElement(root, "mxCell", {"id": "0"})
        SubElement(root, "mxCell", {"id": "1", "parent": "0"})
        for cell in self._cells:
            # fix parent refs to resolve "1" → "1"
            if cell.get("parent") == "1":
                cell.set("parent", "1")
            root.append(cell)

        raw = tostring(mxfile, encoding="unicode")
        return parseString(raw).toprettyxml(indent="  ")


# ── Layout helpers ─────────────────────────────────────────────────────────────
def _short_name(resource: dict, fallback_key: str = "resource_id") -> str:
    name = resource.get("tags", {}).get("Name", "")
    if name:
        return name
    rid = resource.get(fallback_key, resource.get("resource_id", ""))
    # shorten long IDs: keep prefix + last 4 chars
    parts = rid.split("-")
    if len(parts) >= 2:
        return f"{parts[0]}-...{parts[-1][-4:]}"
    return rid[-12:]


def _subnet_height(resource_count: int) -> float:
    rows = max(1, math.ceil(resource_count / RESOURCES_PER_ROW))
    h = (rows * (RESOURCE_H + RESOURCE_LABEL_H + RESOURCE_MARGIN)) + 60
    return max(SUBNET_H_MIN, h)


def _place_resources_in_subnet(
    builder: DrawioBuilder,
    resources: list[tuple[str, str, str]],  # (resource_id, label, style_key)
    subnet_cell_id: str,
    subnet_h: float,
) -> None:
    row_start_x = RESOURCE_MARGIN
    start_y = 35  # leave room for subnet label
    for i, (rid, label, style_key) in enumerate(resources):
        col = i % RESOURCES_PER_ROW
        row = i // RESOURCES_PER_ROW
        x = row_start_x + col * (RESOURCE_W + RESOURCE_MARGIN)
        y = start_y + row * (RESOURCE_H + RESOURCE_LABEL_H + RESOURCE_MARGIN)
        builder.add_vertex(rid, label, STYLES[style_key], x, y, RESOURCE_W, RESOURCE_H, parent=subnet_cell_id)


# ── Main diagram logic ────────────────────────────────────────────────────────
def load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_diagram(account_dir: Path, output_path: Path) -> None:
    # ── Load all data ─────────────────────────────────────────────────────────
    vpcs              = load_json(account_dir / "vpcs.json")
    subnets           = load_json(account_dir / "subnets.json")
    route_tables      = load_json(account_dir / "route_tables.json")
    igws              = load_json(account_dir / "internet_gateways.json")
    nat_gws           = load_json(account_dir / "nat_gateways.json")
    tgw_attachments   = load_json(account_dir / "transit_gateway_attachments.json")
    ec2_instances     = load_json(account_dir / "ec2.json")
    load_balancers    = load_json(account_dir / "load_balancers.json")
    target_groups     = load_json(account_dir / "target_groups.json")
    vpc_endpoints     = load_json(account_dir / "vpc_endpoints.json")

    builder = DrawioBuilder()

    # ── Index helper structures ───────────────────────────────────────────────
    subnet_by_id   = {s["resource_id"]: s for s in subnets}
    igw_by_vpc: dict[str, list[dict]] = {}
    for igw in igws:
        for vpc_id in igw.get("attached_vpc_ids", []):
            igw_by_vpc.setdefault(vpc_id, []).append(igw)

    nat_by_subnet: dict[str, list[dict]] = {}
    nat_by_vpc: dict[str, list[dict]] = {}
    for nat in nat_gws:
        nat_by_subnet.setdefault(nat.get("subnet_id", ""), []).append(nat)
        nat_by_vpc.setdefault(nat.get("vpc_id", ""), []).append(nat)

    ec2_by_subnet: dict[str, list[dict]] = {}
    for inst in ec2_instances:
        if inst.get("state") != "terminated":
            ec2_by_subnet.setdefault(inst.get("subnet_id", ""), []).append(inst)

    alb_by_subnet: dict[str, list[dict]] = {}
    for lb in load_balancers:
        for az in lb.get("availability_zones", []):
            sid = az.get("SubnetId", "")
            if sid:
                alb_by_subnet.setdefault(sid, []).append(lb)

    vpce_by_subnet: dict[str, list[dict]] = {}
    for ep in vpc_endpoints:
        for sid in ep.get("associated_subnet_ids", []):
            vpce_by_subnet.setdefault(sid, []).append(ep)

    # Build ALB arn → EC2 instance_id mapping via target groups
    lb_to_ec2: dict[str, list[str]] = {}
    ec2_instance_ids = {inst["resource_id"] for inst in ec2_instances}
    for tg in target_groups:
        for lb_arn in tg.get("load_balancer_arns", []):
            for target in tg.get("targets", []):
                tid = target.get("id", "")
                if tid in ec2_instance_ids:
                    lb_to_ec2.setdefault(lb_arn, []).append(tid)

    # ── Internet node ─────────────────────────────────────────────────────────
    internet_id = "__internet__"
    builder.add_vertex(
        internet_id, "Internet", STYLES["internet"],
        CANVAS_MARGIN, INTERNET_Y, INTERNET_SIZE, INTERNET_SIZE,
    )

    # ── Layout VPCs ───────────────────────────────────────────────────────────
    current_x = CANVAS_MARGIN

    for vpc in vpcs:
        vpc_id   = vpc["resource_id"]
        vpc_name = _short_name(vpc)
        vpc_cidr = vpc.get("cidr_block", "")

        # Subnets belonging to this VPC
        vpc_subnets = [s for s in subnets if s.get("vpc_id") == vpc_id]
        if not vpc_subnets:
            continue

        # Group by AZ
        az_map: dict[str, list[dict]] = {}
        for s in vpc_subnets:
            az_map.setdefault(s.get("availability_zone", "unknown"), []).append(s)

        # Sort each AZ: public → private → isolated → unknown
        type_order = {"public": 0, "private": 1, "isolated": 2, "unknown": 3}
        for az in az_map:
            az_map[az].sort(key=lambda s: type_order.get(s.get("subnet_type", "unknown"), 3))

        # ── Compute VPC dimensions ────────────────────────────────────────────
        num_azs = len(az_map)
        max_subnets_per_az = max(len(v) for v in az_map.values())

        vpc_w = (
            num_azs * SUBNET_W
            + (num_azs - 1) * SUBNET_GAP
            + 2 * VPC_PADDING
        )
        # Height: top area for IGW/NAT (GATEWAY_MARGIN) + AZ label + subnets
        max_subnet_h = max(
            _subnet_height(
                len(ec2_by_subnet.get(s["resource_id"], []))
                + len(alb_by_subnet.get(s["resource_id"], []))
                + len(nat_by_subnet.get(s["resource_id"], []))
                + len(vpce_by_subnet.get(s["resource_id"], []))
            )
            for slist in az_map.values()
            for s in slist
        )
        vpc_h = (
            GATEWAY_MARGIN
            + AZ_LABEL_H
            + max_subnets_per_az * (max_subnet_h + SUBNET_GAP)
            + 2 * VPC_PADDING
        )

        vpc_y = CANVAS_MARGIN + INTERNET_SIZE + GATEWAY_MARGIN

        vpc_label = f"{vpc_name}&#xa;{vpc_cidr}"
        builder.add_vertex(vpc_id, vpc_label, STYLES["vpc"], current_x, vpc_y, vpc_w, vpc_h)

        # ── IGW ───────────────────────────────────────────────────────────────
        vpc_igws = igw_by_vpc.get(vpc_id, [])
        igw_x = current_x + vpc_w / 2 - GATEWAY_SIZE / 2
        igw_y = vpc_y - GATEWAY_SIZE - 15
        for igw in vpc_igws:
            igw_label = _short_name(igw)
            builder.add_vertex(igw["resource_id"], igw_label, STYLES["igw"], igw_x, igw_y, GATEWAY_SIZE, GATEWAY_SIZE)
            builder.add_edge(internet_id, igw["resource_id"], style=STYLES["edge"])
            builder.add_edge(igw["resource_id"], vpc_id, style=STYLES["edge"])
            igw_x += GATEWAY_SIZE + 20

        # ── TGW attachments ───────────────────────────────────────────────────
        for att in tgw_attachments:
            if att.get("resource_id_ref") == vpc_id or att.get("attachment_type") == "vpc":
                tgw_label = f"TGW&#xa;{_short_name(att)}"
                tgw_node_id = att["resource_id"]
                tgw_x = current_x - GATEWAY_SIZE - 20
                builder.add_vertex(tgw_node_id, tgw_label, STYLES["tgw"], tgw_x, vpc_y + vpc_h / 2, GATEWAY_SIZE, GATEWAY_SIZE)
                builder.add_edge(tgw_node_id, vpc_id, style=STYLES["edge_dashed"])

        # ── Place subnets by AZ (column per AZ) ───────────────────────────────
        for az_idx, (az_name, az_subnets) in enumerate(sorted(az_map.items())):
            az_col_x = VPC_PADDING + az_idx * (SUBNET_W + SUBNET_GAP)

            for sub_idx, subnet in enumerate(az_subnets):
                subnet_id   = subnet["resource_id"]
                subnet_type = subnet.get("subnet_type", "unknown")
                subnet_name = _short_name(subnet)
                cidr        = subnet.get("cidr_block", "")
                style_key   = f"subnet_{subnet_type}"

                # Resources in this subnet
                resources: list[tuple[str, str, str]] = []

                for nat in nat_by_subnet.get(subnet_id, []):
                    resources.append((nat["resource_id"], _short_name(nat), "nat"))

                for lb in alb_by_subnet.get(subnet_id, []):
                    lb_type = lb.get("lb_type", "application")
                    sk = "alb" if lb_type == "application" else "nlb"
                    resources.append((lb["resource_id"], _short_name(lb, "resource_name"), sk))

                for inst in ec2_by_subnet.get(subnet_id, []):
                    resources.append((inst["resource_id"], _short_name(inst), "ec2"))

                for ep in vpce_by_subnet.get(subnet_id, []):
                    svc = ep.get("service_name", "").split(".")[-1]
                    resources.append((ep["resource_id"], svc, "vpce"))

                subnet_h = _subnet_height(len(resources))
                sub_y = VPC_PADDING + AZ_LABEL_H + sub_idx * (subnet_h + SUBNET_GAP)

                subnet_label = f"{subnet_name}&#xa;{cidr}&#xa;{az_name}"
                builder.add_vertex(subnet_id, subnet_label, STYLES[style_key], az_col_x, sub_y, SUBNET_W, subnet_h, parent=vpc_id)
                _place_resources_in_subnet(builder, resources, subnet_id, subnet_h)

        current_x += vpc_w + VPC_GAP

    # ── ALB → EC2 edges ───────────────────────────────────────────────────────
    drawn_edges: set[tuple[str, str]] = set()
    for lb_arn, ec2_ids in lb_to_ec2.items():
        for ec2_id in set(ec2_ids):
            pair = (lb_arn, ec2_id)
            if pair not in drawn_edges:
                builder.add_edge(lb_arn, ec2_id, style=STYLES["edge_dashed"])
                drawn_edges.add(pair)

    # ── Write output ──────────────────────────────────────────────────────────
    xml_str = builder.to_xml()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml_str)
    print(f"Diagram written → {output_path}")
    print(f"Open at: https://app.diagrams.net/")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate draw.io diagram from jericho-extractor output")
    parser.add_argument("--account", required=True, help="Account name (folder inside output/)")
    parser.add_argument("--output-dir", default="output", help="Base output directory (default: output)")
    args = parser.parse_args()

    account_dir  = Path(args.output_dir) / args.account
    output_path  = account_dir / "network_diagram.drawio"

    if not account_dir.exists():
        print(f"Error: account directory not found: {account_dir}")
        raise SystemExit(1)

    build_diagram(account_dir, output_path)


if __name__ == "__main__":
    main()
