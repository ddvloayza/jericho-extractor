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
CANVAS_X          = 80
CANVAS_Y          = 80
VPC_PADDING_X     = 50
VPC_PADDING_TOP   = 90
VPC_PADDING_BOT   = 40
VPC_GAP           = 120

AZ_GAP            = 20
SUBNET_W          = 380       # wider to fit full names
SUBNET_GAP        = 16
SUBNET_H_MIN      = 160
SUBNET_LABEL_H    = 46

RESOURCE_W        = 56        # icon square
RESOURCE_H        = 56
RESOURCE_LABEL_H  = 0         # label goes BELOW via verticalLabelPosition
RESOURCE_CELL_H   = 90        # total cell height (icon 56 + label area 34)
RESOURCE_MARGIN_X = 18
RESOURCE_MARGIN_Y = 14
RESOURCES_PER_ROW = 3

GATEWAY_W         = 60
GATEWAY_H         = 60
INTERNET_W        = 64
INTERNET_H        = 64


# ── AWS draw.io styles ────────────────────────────────────────────────────────
def _icon(res_icon: str, fill: str) -> str:
    """Icon with label rendered below the shape (not overlapping)."""
    return (
        f"outlineConnect=0;fontColor=#232F3E;gradientColor=none;strokeColor=none;"
        f"fillColor={fill};labelBackgroundColor=#ffffff;"
        f"align=center;verticalLabelPosition=bottom;verticalAlign=top;"
        f"html=1;fontSize=8;fontStyle=0;aspect=fixed;"
        f"shape=mxgraph.aws4.resourceIcon;resIcon={res_icon};"
    )


def _group(gr_icon: str, fill: str, stroke: str, font_size: int = 9) -> str:
    return (
        f"points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],"
        f"[1,1],[0.75,1],[0.5,1],[0.25,1],[0,1],[0,0.75],[0,0.5],[0,0.25]];"
        f"shape=mxgraph.aws4.group;grIcon={gr_icon};"
        f"verticalLabelPosition=top;verticalAlign=bottom;"
        f"fillColor={fill};strokeColor={stroke};"
        f"fontSize={font_size};fontStyle=1;spacingTop=5;html=0;"
    )


STYLES: dict[str, str] = {
    "vpc":             _group("mxgraph.aws4.group_vpc",             "#E6F3FF", "#147EBA", 10),
    "subnet_public":   _group("mxgraph.aws4.group_public_subnet",   "#E8F5E9", "#2E7D32"),
    "subnet_private":  _group("mxgraph.aws4.group_private_subnet",  "#FFF9C4", "#F57F17"),
    "subnet_isolated": _group("mxgraph.aws4.group_private_subnet",  "#FFEBEE", "#C62828"),
    "subnet_unknown":  _group("mxgraph.aws4.group_private_subnet",  "#F5F5F5", "#9E9E9E"),
    "igw":    _icon("mxgraph.aws4.internet_gateway",          "#8C4FFF"),
    "nat":    _icon("mxgraph.aws4.nat_gateway",               "#8C4FFF"),
    "tgw":    _icon("mxgraph.aws4.transit_gateway",           "#8C4FFF"),
    "vpce":   _icon("mxgraph.aws4.vpc_endpoints",             "#8C4FFF"),
    "ec2":    _icon("mxgraph.aws4.ec2",                       "#ED7100"),
    "alb":    _icon("mxgraph.aws4.application_load_balancer", "#E7157B"),
    "nlb":    _icon("mxgraph.aws4.network_load_balancer",     "#E7157B"),
    "eks":    _icon("mxgraph.aws4.eks",                       "#ED7100"),
    "eks_ng": _icon("mxgraph.aws4.eks",                       "#F0A500"),
    "internet": (
        "shape=mxgraph.aws4.internet_alt2;fillColor=#232F3E;strokeColor=none;"
        "fontColor=#232F3E;gradientColor=none;labelBackgroundColor=#ffffff;"
        "align=center;verticalLabelPosition=bottom;verticalAlign=top;"
        "html=1;fontSize=8;fontStyle=1;aspect=fixed;"
    ),
    "edge_solid": (
        "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;"
        "jettySize=auto;strokeColor=#444444;strokeWidth=1.5;"
        "exitX=0.5;exitY=1;exitDx=0;exitDy=0;"
        "entryX=0.5;entryY=0;entryDx=0;entryDy=0;"
    ),
    "edge_dashed": (
        "edgeStyle=orthogonalEdgeStyle;rounded=1;dashed=1;dashPattern=6 3;"
        "strokeColor=#888888;strokeWidth=1;"
    ),
    "edge_k8s": (
        "edgeStyle=orthogonalEdgeStyle;rounded=1;dashed=1;dashPattern=4 2;"
        "strokeColor=#3949AB;strokeWidth=1.5;fontColor=#3949AB;fontSize=7;"
    ),
    "k8s_cluster_group": (
        "rounded=1;whiteSpace=wrap;arcSize=3;"
        "fillColor=#E0F7FA;strokeColor=#00838F;strokeWidth=2;"
        "fontStyle=1;fontSize=9;verticalAlign=top;spacingTop=4;html=1;"
    ),
    "k8s_namespace": (
        "rounded=1;whiteSpace=wrap;arcSize=5;"
        "fillColor=#E8EAF6;strokeColor=#3949AB;strokeWidth=1.5;"
        "fontStyle=1;fontSize=8;verticalAlign=top;spacingTop=4;html=1;"
    ),
    "k8s_deploy": _icon("mxgraph.aws4.ec2",                       "#3949AB"),
    "k8s_svc":    _icon("mxgraph.aws4.application_load_balancer", "#00838F"),
    "k8s_ingress":_icon("mxgraph.aws4.application_load_balancer", "#6A1B9A"),
}

# ── Kubernetes layout constants ───────────────────────────────────────────────
K8S_CLUSTER_PADDING   = 30
K8S_CLUSTER_LABEL_H   = 50
K8S_CLUSTER_GAP       = 60
K8S_NS_W              = 400        # wider to fit more icons per row
K8S_NS_LABEL_H        = 38
K8S_NS_GAP            = 16
K8S_RESOURCES_PER_ROW = 5          # more columns → shorter namespaces
K8S_NS_PER_ROW        = 4          # max namespaces side-by-side in cluster group


# ── XML builder ───────────────────────────────────────────────────────────────
class DrawioBuilder:
    def __init__(self) -> None:
        self._counter = 10
        self._id_map: dict[str, str] = {}
        self._cells: list[Element] = []
        self._added: set[str] = set()   # track resource_ids already materialized

    def _next_id(self) -> str:
        cid = str(self._counter)
        self._counter += 1
        return cid

    def cell_id(self, resource_id: str) -> str:
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
        parent_id: str = "1",
    ) -> str:
        if resource_id in self._added:
            return self._id_map[resource_id]
        self._added.add(resource_id)
        cid = self.cell_id(resource_id)
        parent_cid = self._id_map.get(parent_id, parent_id)
        cell = Element("mxCell", {
            "id": cid,
            "value": label,
            "style": style,
            "vertex": "1",
            "parent": parent_cid,
        })
        SubElement(cell, "mxGeometry", {
            "x": str(int(round(x))),
            "y": str(int(round(y))),
            "width": str(int(round(w))),
            "height": str(int(round(h))),
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
    ) -> None:
        src = self._id_map.get(source_id)
        tgt = self._id_map.get(target_id)
        if not src or not tgt:
            return
        eid = self._next_id()
        cell = Element("mxCell", {
            "id": eid,
            "value": label,
            "style": style or STYLES["edge_solid"],
            "edge": "1",
            "source": src,
            "target": tgt,
            "parent": "1",
        })
        SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
        self._cells.append(cell)

    def to_xml(self) -> str:
        mxfile = Element("mxfile", {"host": "jericho-extractor"})
        diagram = SubElement(mxfile, "diagram", {"name": "Network Topology"})
        model = SubElement(diagram, "mxGraphModel", {
            "dx": "1422", "dy": "762",
            "grid": "1", "gridSize": "10",
            "guides": "1", "tooltips": "1",
            "connect": "1", "arrows": "1",
            "fold": "1", "page": "1",
            "pageScale": "1", "pageWidth": "3300", "pageHeight": "2338",
            "math": "0", "shadow": "0",
        })
        root = SubElement(model, "root")
        SubElement(root, "mxCell", {"id": "0"})
        SubElement(root, "mxCell", {"id": "1", "parent": "0"})
        for cell in self._cells:
            root.append(cell)
        raw = tostring(mxfile, encoding="unicode")
        return parseString(raw).toprettyxml(indent="  ")


# ── Type labels shown under each icon ────────────────────────────────────────
TYPE_LABELS: dict[str, str] = {
    "nat":         "NAT Gateway",
    "alb":         "App Load Balancer",
    "nlb":         "Net Load Balancer",
    "ec2":         "EC2 Instance",
    "vpce":        "VPC Endpoint",
    "eks":         "EKS Cluster",
    "eks_ng":      "Node Group",
    "igw":         "Internet Gateway",
    "tgw":         "Transit Gateway",
    "k8s_deploy":  "Deployment",
    "k8s_svc":     "Service",
    "k8s_ingress": "Ingress",
}


def _typed(name: str, type_key: str) -> str:
    """Append a small grey type subtitle to an icon label (HTML)."""
    tl = TYPE_LABELS.get(type_key, "")
    if not tl:
        return name
    return f'{name}<br><font style="font-size:7px;color:#888888;">{tl}</font>'


# ── Helpers ───────────────────────────────────────────────────────────────────
def load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def full_name(resource: dict, name_key: str = "resource_id") -> str:
    """Return the Name tag (full, no truncation) or the resource identifier."""
    tag_name = resource.get("tags", {}).get("Name", "")
    if tag_name:
        return tag_name
    # For EKS/LB use resource_name field when available
    rname = resource.get("resource_name", "")
    if rname:
        return rname
    return resource.get(name_key) or resource.get("resource_id", "")


def subnet_height(n_resources: int) -> int:
    rows = max(1, math.ceil(n_resources / RESOURCES_PER_ROW))
    return max(SUBNET_H_MIN, SUBNET_LABEL_H + rows * (RESOURCE_CELL_H + RESOURCE_MARGIN_Y) + RESOURCE_MARGIN_Y)


def place_resources(
    builder: DrawioBuilder,
    items: list[tuple[str, str, str]],
    parent_id: str,
    container_w: int = SUBNET_W,
) -> None:
    slot_w = RESOURCE_W + RESOURCE_MARGIN_X * 2
    for i, (rid, label, sk) in enumerate(items):
        col = i % RESOURCES_PER_ROW
        row = i // RESOURCES_PER_ROW
        row_start  = row * RESOURCES_PER_ROW
        row_count  = min(RESOURCES_PER_ROW, len(items) - row_start)
        start_x    = max(0, (container_w - row_count * slot_w) / 2)
        x = start_x + col * slot_w + RESOURCE_MARGIN_X
        y = SUBNET_LABEL_H + row * (RESOURCE_CELL_H + RESOURCE_MARGIN_Y)
        builder.add_vertex(rid, _typed(label, sk), STYLES[sk], x, y, RESOURCE_W, RESOURCE_CELL_H, parent_id=parent_id)


# ── Core diagram builder ──────────────────────────────────────────────────────
def build_diagram(account_dir: Path, output_path: Path) -> None:
    vpcs                 = load_json(account_dir / "vpcs.json")
    subnets              = load_json(account_dir / "subnets.json")
    igws                 = load_json(account_dir / "internet_gateways.json")
    nat_gws              = load_json(account_dir / "nat_gateways.json")
    tgw_attachments      = load_json(account_dir / "transit_gateway_attachments.json")
    ec2_instances        = load_json(account_dir / "ec2.json")
    load_balancers       = load_json(account_dir / "load_balancers.json")
    target_groups        = load_json(account_dir / "target_groups.json")
    vpc_endpoints        = load_json(account_dir / "vpc_endpoints.json")
    eks_resources        = load_json(account_dir / "eks.json")
    kubernetes_workloads = load_json(account_dir / "kubernetes_workloads.json")

    builder = DrawioBuilder()

    # ── Indexes ───────────────────────────────────────────────────────────────
    igw_by_vpc: dict[str, list[dict]] = {}
    for igw in igws:
        for vid in igw.get("attached_vpc_ids", []):
            igw_by_vpc.setdefault(vid, []).append(igw)

    nat_by_subnet: dict[str, list[dict]] = {}
    for nat in nat_gws:
        nat_by_subnet.setdefault(nat.get("subnet_id", ""), []).append(nat)

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

    # EKS clusters (not nodegroups) per VPC
    eks_clusters = [r for r in eks_resources if r.get("resource_type") == "aws::eks::cluster"]
    eks_nodegroups = [r for r in eks_resources if r.get("resource_type") == "aws::eks::nodegroup"]

    eks_by_vpc: dict[str, list[dict]] = {}
    for cl in eks_clusters:
        eks_by_vpc.setdefault(cl.get("vpc_id", ""), []).append(cl)

    eks_ng_by_subnet: dict[str, list[dict]] = {}
    for ng in eks_nodegroups:
        for sid in ng.get("subnet_ids", []):
            eks_ng_by_subnet.setdefault(sid, []).append(ng)

    # LB → EC2 via target groups (instance-id AND ip targets)
    ec2_ids_set = {i["resource_id"] for i in ec2_instances}
    ec2_by_ip:  dict[str, str] = {i["private_ip"]: i["resource_id"]
                                   for i in ec2_instances if i.get("private_ip")}
    lb_to_ec2: dict[str, list[str]] = {}
    for tg in target_groups:
        for lb_arn in tg.get("load_balancer_arns", []):
            for t in tg.get("targets", []):
                tid = t.get("id", "")
                if tid in ec2_ids_set:
                    lb_to_ec2.setdefault(lb_arn, []).append(tid)
                elif tid in ec2_by_ip:
                    lb_to_ec2.setdefault(lb_arn, []).append(ec2_by_ip[tid])

    # ALB → EKS cluster (detect kubernetes-managed ALBs by tag)
    # AWS LBC uses elbv2.k8s.aws/cluster=<name> or kubernetes.io/cluster/<name>=owned
    lb_to_eks: dict[str, str] = {}
    eks_by_name = {c.get("cluster_name", ""): c["resource_id"] for c in eks_clusters}
    for lb in load_balancers:
        tags = lb.get("tags", {})
        cluster_name = ""
        # New-style tag (AWS Load Balancer Controller)
        if "elbv2.k8s.aws/cluster" in tags:
            cluster_name = tags["elbv2.k8s.aws/cluster"]
        else:
            # Old-style tag: kubernetes.io/cluster/<name> = owned|shared
            for tag_key in tags:
                if tag_key.startswith("kubernetes.io/cluster/"):
                    cluster_name = tag_key.split("/")[-1]
                    break
        if cluster_name and cluster_name in eks_by_name:
            lb_to_eks[lb["resource_id"]] = eks_by_name[cluster_name]

    # TGW attachments per VPC
    tgw_by_vpc: dict[str, list[dict]] = {}
    for att in tgw_attachments:
        if att.get("attachment_type") == "vpc":
            tgw_by_vpc.setdefault(att.get("resource_id_ref", ""), []).append(att)

    # ALB by dns_name (for ingress → ALB matching)
    alb_by_dns: dict[str, str] = {}
    for lb in load_balancers:
        dns = lb.get("dns_name", "")
        if dns:
            alb_by_dns[dns] = lb["resource_id"]

    # Kubernetes workloads indexed by cluster_arn and resource_type
    k8s_by_cluster: dict[str, list[dict]] = {}
    for w in kubernetes_workloads:
        k8s_by_cluster.setdefault(w.get("cluster_arn", ""), []).append(w)

    # ── Internet node ─────────────────────────────────────────────────────────
    internet_id = "__internet__"
    builder.add_vertex(internet_id, "Internet", STYLES["internet"], CANVAS_X, CANVAS_Y, INTERNET_W, INTERNET_H)

    # ── Layout each VPC ───────────────────────────────────────────────────────
    cursor_x = CANVAS_X
    max_vpc_bottom = CANVAS_Y

    for vpc in vpcs:
        vpc_id   = vpc["resource_id"]
        vpc_name = full_name(vpc)
        vpc_cidr = vpc.get("cidr_block", "")

        vpc_subnets = [s for s in subnets if s.get("vpc_id") == vpc_id]
        if not vpc_subnets:
            continue

        type_order = {"public": 0, "private": 1, "isolated": 2, "unknown": 3}
        az_map: dict[str, list[dict]] = {}
        for s in vpc_subnets:
            az_map.setdefault(s.get("availability_zone", "?"), []).append(s)
        for az in az_map:
            az_map[az].sort(key=lambda s: type_order.get(s.get("subnet_type", "unknown"), 3))

        num_azs = len(az_map)

        def _res_count(sid: str) -> int:
            return (
                len(nat_by_subnet.get(sid, []))
                + len(alb_by_subnet.get(sid, []))
                + len(ec2_by_subnet.get(sid, []))
                + len(vpce_by_subnet.get(sid, []))
                + len(eks_ng_by_subnet.get(sid, []))
            )

        sub_heights = {s["resource_id"]: subnet_height(_res_count(s["resource_id"])) for s in vpc_subnets}

        az_col_heights = {
            az: sum(sub_heights[s["resource_id"]] for s in sl) + SUBNET_GAP * (len(sl) - 1)
            for az, sl in az_map.items()
        }
        max_col_h = max(az_col_heights.values())

        vpc_inner_w = num_azs * SUBNET_W + (num_azs - 1) * AZ_GAP
        vpc_w = vpc_inner_w + 2 * VPC_PADDING_X
        vpc_h = max_col_h + VPC_PADDING_TOP + VPC_PADDING_BOT

        # Extra height for EKS cluster icons at top of VPC
        n_eks = len(eks_by_vpc.get(vpc_id, []))
        if n_eks:
            vpc_h += RESOURCE_CELL_H + 20

        igw_area_h = INTERNET_H + 50 + GATEWAY_H
        vpc_y = CANVAS_Y + igw_area_h + 20

        vpc_label = f"{vpc_name}\n{vpc_cidr}"
        builder.add_vertex(vpc_id, vpc_label, STYLES["vpc"], cursor_x, vpc_y, vpc_w, vpc_h)

        # ── IGW(s) ────────────────────────────────────────────────────────────
        vpc_igws = igw_by_vpc.get(vpc_id, [])
        igw_total_w = len(vpc_igws) * GATEWAY_W + max(0, len(vpc_igws) - 1) * 20
        igw_start_x = cursor_x + vpc_w / 2 - igw_total_w / 2
        igw_y = vpc_y - GATEWAY_H - 20

        for k, igw in enumerate(vpc_igws):
            igw_x = igw_start_x + k * (GATEWAY_W + 20)
            builder.add_vertex(igw["resource_id"], _typed(full_name(igw), "igw"), STYLES["igw"], igw_x, igw_y, GATEWAY_W, GATEWAY_H)
            builder.add_edge(internet_id, igw["resource_id"], style=STYLES["edge_solid"])
            builder.add_edge(igw["resource_id"], vpc_id, style=STYLES["edge_solid"])

        # ── TGW attachment ────────────────────────────────────────────────────
        for att in tgw_by_vpc.get(vpc_id, []):
            tgw_x = cursor_x + vpc_w + 24
            tgw_y = vpc_y + vpc_h / 2 - GATEWAY_H / 2
            builder.add_vertex(att["resource_id"], _typed(full_name(att), "tgw"), STYLES["tgw"], tgw_x, tgw_y, GATEWAY_W, GATEWAY_H)
            builder.add_edge(vpc_id, att["resource_id"], style=STYLES["edge_dashed"])

        # ── EKS clusters at top of VPC (outside subnets) ──────────────────────
        eks_in_vpc = eks_by_vpc.get(vpc_id, [])
        for k, cluster in enumerate(eks_in_vpc):
            eks_x = VPC_PADDING_X + k * (RESOURCE_W + 30)
            eks_y = 10
            builder.add_vertex(
                cluster["resource_id"],
                _typed(cluster.get("cluster_name", full_name(cluster)), "eks"),
                STYLES["eks"],
                eks_x, eks_y, RESOURCE_W, RESOURCE_CELL_H,
                parent_id=vpc_id,
            )

        # ── Subnets — column per AZ ───────────────────────────────────────────
        for az_idx, (az_name, az_subnets) in enumerate(sorted(az_map.items())):
            col_x = VPC_PADDING_X + az_idx * (SUBNET_W + AZ_GAP)
            # Push down if EKS clusters take space at top
            row_y = VPC_PADDING_TOP + (RESOURCE_CELL_H + 20 if n_eks else 0)

            for subnet in az_subnets:
                sid    = subnet["resource_id"]
                stype  = subnet.get("subnet_type", "unknown")
                scidr  = subnet.get("cidr_block", "")
                sname  = full_name(subnet)
                az_short = az_name.split("-")[-1] if "-" in az_name else az_name
                sub_label = f"{sname}\n{scidr}  [{az_short}]"
                sub_h  = sub_heights[sid]

                builder.add_vertex(sid, sub_label, STYLES[f"subnet_{stype}"], col_x, row_y, SUBNET_W, sub_h, parent_id=vpc_id)

                items: list[tuple[str, str, str]] = []
                for nat in nat_by_subnet.get(sid, []):
                    items.append((nat["resource_id"], full_name(nat), "nat"))
                for lb in alb_by_subnet.get(sid, []):
                    sk = "alb" if lb.get("lb_type", "application") == "application" else "nlb"
                    items.append((lb["resource_id"], full_name(lb, "resource_name"), sk))
                for inst in ec2_by_subnet.get(sid, []):
                    items.append((inst["resource_id"], full_name(inst), "ec2"))
                for ep in vpce_by_subnet.get(sid, []):
                    svc = ep.get("service_name", "").split(".")[-1]
                    items.append((ep["resource_id"], svc or full_name(ep), "vpce"))
                for ng in eks_ng_by_subnet.get(sid, []):
                    items.append((ng["resource_id"], ng.get("nodegroup_name", full_name(ng)), "eks_ng"))

                place_resources(builder, items, parent_id=sid)
                row_y += sub_h + SUBNET_GAP

        max_vpc_bottom = max(max_vpc_bottom, vpc_y + vpc_h)
        cursor_x += vpc_w + VPC_GAP

    # ── Edges: Node Group → EKS cluster ──────────────────────────────────────
    for ng in eks_nodegroups:
        builder.add_edge(ng["resource_id"], ng["cluster_arn"], style=STYLES["edge_dashed"])

    # ── Edges: ALB → EC2 (instance targets) ──────────────────────────────────
    drawn: set[tuple[str, str]] = set()
    for lb_arn, targets in lb_to_ec2.items():
        for ec2_id in set(targets):
            if (lb_arn, ec2_id) not in drawn:
                builder.add_edge(lb_arn, ec2_id, style=STYLES["edge_dashed"])
                drawn.add((lb_arn, ec2_id))

    # ── Edges: ALB → EKS cluster (kubernetes-managed ALBs) ────────────────────
    for lb_arn, cluster_arn in lb_to_eks.items():
        builder.add_edge(lb_arn, cluster_arn, label="k8s", style=STYLES["edge_dashed"])

    # ── Kubernetes workloads section ──────────────────────────────────────────
    if kubernetes_workloads:
        k8s_row_y = max_vpc_bottom + 120
        k8s_cursor_x = CANVAS_X

        for cluster in eks_clusters:
            cluster_arn  = cluster["resource_id"]
            cluster_name = cluster.get("cluster_name", full_name(cluster))
            workloads    = k8s_by_cluster.get(cluster_arn, [])
            if not workloads:
                continue

            # Separate by type
            namespaces  = [w for w in workloads if w.get("resource_type") == "aws::eks::k8s_namespace"]
            deployments = [w for w in workloads if w.get("resource_type") == "aws::eks::k8s_deployment"]
            services    = [w for w in workloads if w.get("resource_type") == "aws::eks::k8s_service"]
            ingresses   = [w for w in workloads if w.get("resource_type") == "aws::eks::k8s_ingress"]

            # Group deployments/services/ingresses by namespace
            ns_items: dict[str, list[tuple[str, str, str]]] = {}
            for ns in namespaces:
                ns_items[ns["resource_name"]] = []
            for dep in deployments:
                ns_items.setdefault(dep.get("namespace", "default"), []).append(
                    (dep["resource_id"], dep.get("resource_name", ""), "k8s_deploy")
                )
            for svc in services:
                if svc.get("service_type") != "ClusterIP":
                    ns_items.setdefault(svc.get("namespace", "default"), []).append(
                        (svc["resource_id"], svc.get("resource_name", ""), "k8s_svc")
                    )
            for ing in ingresses:
                ns_items.setdefault(ing.get("namespace", "default"), []).append(
                    (ing["resource_id"], ing.get("resource_name", ""), "k8s_ingress")
                )

            # Drop empty system namespaces to reduce noise
            SYSTEM_NS = {"kube-system", "kube-public", "kube-node-lease"}
            ns_items = {k: v for k, v in ns_items.items() if v or k not in SYSTEM_NS}

            if not ns_items:
                continue

            # Calculate namespace heights (5 icons per row → shorter boxes)
            def _ns_h(items: list) -> int:
                rows = max(1, math.ceil(len(items) / K8S_RESOURCES_PER_ROW)) if items else 0
                return max(110, K8S_NS_LABEL_H + rows * (RESOURCE_CELL_H + RESOURCE_MARGIN_Y) + RESOURCE_MARGIN_Y)

            # Sort: namespaces with items first, then alphabetical
            ns_list = sorted(ns_items.keys(), key=lambda n: (len(ns_items[n]) == 0, n))
            ns_heights = {ns: _ns_h(ns_items[ns]) for ns in ns_list}

            # Grid layout: K8S_NS_PER_ROW namespaces per row
            ns_cols = min(K8S_NS_PER_ROW, len(ns_list))
            ns_row_count = math.ceil(len(ns_list) / ns_cols)

            # Cluster width = widest row of namespaces
            cluster_inner_w = ns_cols * (K8S_NS_W + K8S_NS_GAP) - K8S_NS_GAP
            cluster_w = cluster_inner_w + 2 * K8S_CLUSTER_PADDING

            # Cluster height = sum of max-height per namespace row
            def _row_max_h(row_idx: int) -> int:
                start = row_idx * ns_cols
                end   = min(start + ns_cols, len(ns_list))
                return max(ns_heights[ns_list[i]] for i in range(start, end))

            cluster_h = (
                K8S_CLUSTER_LABEL_H
                + sum(_row_max_h(r) for r in range(ns_row_count))
                + (ns_row_count - 1) * K8S_NS_GAP
                + K8S_CLUSTER_PADDING
            )

            cg_id = f"__k8s_group_{cluster_arn}__"
            builder.add_vertex(
                cg_id,
                f"EKS: {cluster_name}",
                STYLES["k8s_cluster_group"],
                k8s_cursor_x, k8s_row_y, cluster_w, cluster_h,
            )
            builder.add_edge(cluster_arn, cg_id, style=STYLES["edge_dashed"])

            for ns_idx, ns_name in enumerate(ns_list):
                col = ns_idx % ns_cols
                row = ns_idx // ns_cols

                # Absolute y inside cluster group: sum of previous rows' max heights
                ns_y = K8S_CLUSTER_LABEL_H + sum(
                    _row_max_h(r) + K8S_NS_GAP for r in range(row)
                )
                ns_x = K8S_CLUSTER_PADDING + col * (K8S_NS_W + K8S_NS_GAP)

                ns_id = f"__k8s_ns_{cluster_arn}_{ns_name}__"
                builder.add_vertex(
                    ns_id, ns_name, STYLES["k8s_namespace"],
                    ns_x, ns_y, K8S_NS_W, ns_heights[ns_name],
                    parent_id=cg_id,
                )
                for i, (rid, label, sk) in enumerate(ns_items[ns_name]):
                    col_r = i % K8S_RESOURCES_PER_ROW
                    row_r = i // K8S_RESOURCES_PER_ROW
                    rx = RESOURCE_MARGIN_X + col_r * (RESOURCE_W + RESOURCE_MARGIN_X * 2)
                    ry = K8S_NS_LABEL_H + row_r * (RESOURCE_CELL_H + RESOURCE_MARGIN_Y)
                    builder.add_vertex(rid, _typed(label, sk), STYLES[sk], rx, ry, RESOURCE_W, RESOURCE_CELL_H, parent_id=ns_id)

            k8s_cursor_x += cluster_w + K8S_CLUSTER_GAP

        # ── Edges: Ingress → ALB (via alb_hostname) ───────────────────────────
        for ing in [w for w in kubernetes_workloads if w.get("resource_type") == "aws::eks::k8s_ingress"]:
            hostname = ing.get("alb_hostname", "")
            if hostname and hostname in alb_by_dns:
                lb_id = alb_by_dns[hostname]
                builder.add_edge(
                    ing["resource_id"], lb_id,
                    label="routes to",
                    style=STYLES["edge_k8s"],
                )

    # ── Write ─────────────────────────────────────────────────────────────────
    xml_str = builder.to_xml()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml_str)

    print(f"Diagram written → {output_path}")
    print("Open at: https://app.diagrams.net  (File → Open from Device)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate draw.io diagram from jericho-extractor output")
    parser.add_argument("--account",    required=True, help="Account folder name inside output/")
    parser.add_argument("--output-dir", default="output", help="Base output directory (default: output)")
    args = parser.parse_args()

    account_dir = Path(args.output_dir) / args.account
    output_path = account_dir / "network_diagram.drawio"

    if not account_dir.exists():
        print(f"Error: directory not found: {account_dir}")
        raise SystemExit(1)

    build_diagram(account_dir, output_path)


if __name__ == "__main__":
    main()
