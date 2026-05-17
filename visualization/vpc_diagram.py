from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

from visualization.topology_renderer import TopologyRenderer

logger = logging.getLogger(__name__)

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyBboxPatch
    _MPL_AVAILABLE = True
except ImportError:
    _MPL_AVAILABLE = False


# Layout constants
VPC_PAD        = 1.0
SUBNET_PAD     = 0.4
SUBNET_W       = 4.0
SUBNET_H       = 3.0
SUBNET_GAP     = 0.5
AZ_GAP         = 0.8
RESOURCE_R     = 0.18
RESOURCE_COLS  = 4

SUBNET_COLORS = {
    "public":   ("#E8F5E9", "#2E7D32"),
    "private":  ("#FFF9C4", "#F57F17"),
    "isolated": ("#FFEBEE", "#C62828"),
    "unknown":  ("#F5F5F5", "#9E9E9E"),
}

VPC_COLOR      = ("#E3F2FD", "#1565C0")
GATEWAY_COLOR  = "#6A1B9A"
RESOURCE_ALPHA = 0.85


class VPCDiagram(TopologyRenderer):
    """Renders a VPC topology diagram: VPCs → AZs → subnets → resources.

    Outputs PNG or SVG.
    """

    def render(
        self,
        inventory: dict[str, list[dict[str, Any]]],
        output_path: Path,
        title: str = "VPC Topology",
    ) -> None:
        if not _MPL_AVAILABLE:
            logger.warning("matplotlib required for VPC diagram — skipping")
            return

        vpcs           = inventory.get("vpcs", [])
        subnets        = inventory.get("subnets", [])
        ec2_instances  = [i for i in inventory.get("ec2", []) if i.get("state") != "terminated"]
        load_balancers = inventory.get("load_balancers", [])
        nat_gws        = inventory.get("nat_gateways", [])
        igws           = inventory.get("internet_gateways", [])
        vpc_endpoints  = inventory.get("vpc_endpoints", [])
        eks_clusters   = [r for r in inventory.get("eks", []) if r.get("resource_type") == "aws::eks::cluster"]

        if not vpcs:
            logger.warning("No VPCs found — skipping VPC diagram")
            return

        # Build indexes
        subs_by_vpc: dict[str, list[dict]] = {}
        for s in subnets:
            subs_by_vpc.setdefault(s.get("vpc_id", ""), []).append(s)

        ec2_by_subnet: dict[str, list[dict]] = {}
        for i in ec2_instances:
            ec2_by_subnet.setdefault(i.get("subnet_id", ""), []).append(i)

        alb_by_subnet: dict[str, list[dict]] = {}
        for lb in load_balancers:
            for az in lb.get("availability_zones", []):
                sid = az.get("SubnetId", "")
                if sid:
                    alb_by_subnet.setdefault(sid, []).append(lb)

        nat_by_subnet: dict[str, list[dict]] = {}
        for nat in nat_gws:
            nat_by_subnet.setdefault(nat.get("subnet_id", ""), []).append(nat)

        igw_by_vpc: dict[str, list[dict]] = {}
        for igw in igws:
            for vid in igw.get("attached_vpc_ids", []):
                igw_by_vpc.setdefault(vid, []).append(igw)

        ep_by_subnet: dict[str, list[dict]] = {}
        for ep in vpc_endpoints:
            for sid in ep.get("associated_subnet_ids", []):
                ep_by_subnet.setdefault(sid, []).append(ep)

        eks_by_vpc: dict[str, list[dict]] = {}
        for cl in eks_clusters:
            eks_by_vpc.setdefault(cl.get("vpc_id", ""), []).append(cl)

        # Calculate canvas size
        total_w = 0.0
        vpc_layouts: list[dict] = []

        for vpc in vpcs:
            vpc_id    = vpc["resource_id"]
            vpc_subs  = subs_by_vpc.get(vpc_id, [])
            if not vpc_subs:
                continue
            az_map: dict[str, list[dict]] = {}
            for s in vpc_subs:
                az_map.setdefault(s.get("availability_zone", "?"), []).append(s)

            n_azs     = len(az_map)
            n_subs    = max(len(sl) for sl in az_map.values()) if az_map else 1
            vpc_inner = n_azs * SUBNET_W + (n_azs - 1) * AZ_GAP
            vpc_w     = vpc_inner + 2 * VPC_PAD
            vpc_h     = n_subs * (SUBNET_H + SUBNET_GAP) + 2 * VPC_PAD + 1.5

            vpc_layouts.append({
                "vpc":    vpc,
                "az_map": az_map,
                "x":      total_w,
                "w":      vpc_w,
                "h":      vpc_h,
            })
            total_w += vpc_w + 2.0

        canvas_h = max((v["h"] for v in vpc_layouts), default=10) + 4
        fig, ax  = self._new_figure(w=max(total_w + 2, 16), h=canvas_h)
        fig.patch.set_facecolor("#0D1117")
        ax.set_facecolor("#0D1117")
        ax.set_xlim(-1, total_w + 1)
        ax.set_ylim(-2, canvas_h)

        # Draw Internet globe
        ax.plot(total_w / 2, canvas_h - 1.2, "o", markersize=28, color="#232F3E", zorder=5)
        ax.text(total_w / 2, canvas_h - 1.2, "🌐", ha="center", va="center", fontsize=14, zorder=6)
        ax.text(total_w / 2, canvas_h - 2.0, "Internet", ha="center", va="center",
                fontsize=8, color="white", fontweight="bold")

        for layout in vpc_layouts:
            vpc    = layout["vpc"]
            vpc_id = vpc["resource_id"]
            az_map = layout["az_map"]
            vx     = layout["x"]
            vw     = layout["w"]
            vh     = layout["h"]
            vpc_name = self._short_label(vpc)
            vpc_cidr = vpc.get("cidr_block", "")

            # VPC box
            vpc_fill, vpc_stroke = VPC_COLOR
            vpc_patch = FancyBboxPatch(
                (vx, 0), vw, vh,
                boxstyle="round,pad=0.1",
                facecolor=vpc_fill, edgecolor=vpc_stroke, linewidth=2, alpha=0.25,
            )
            ax.add_patch(vpc_patch)
            ax.text(vx + vw / 2, vh + 0.15, f"{vpc_name}  {vpc_cidr}",
                    ha="center", va="bottom", fontsize=8, color="#90CAF9", fontweight="bold")

            # IGW arrow from internet
            if igw_by_vpc.get(vpc_id):
                ax.annotate(
                    "", xy=(vx + vw / 2, vh), xytext=(total_w / 2, canvas_h - 2.2),
                    arrowprops=dict(arrowstyle="->", color=GATEWAY_COLOR, lw=1.5),
                )
                ax.text(vx + vw / 2, vh + 0.6, "IGW", ha="center", fontsize=7, color=GATEWAY_COLOR)

            # EKS cluster badge
            for k, cl in enumerate(eks_by_vpc.get(vpc_id, [])):
                cx = vx + VPC_PAD + k * 1.8
                ax.plot(cx, 0.35, "s", markersize=12, color="#F57F17", zorder=4, alpha=0.9)
                ax.text(cx, 0.35, "EKS", ha="center", va="center", fontsize=5, color="white", fontweight="bold")
                ax.text(cx, -0.05, cl.get("cluster_name", "")[:16], ha="center", fontsize=5, color="#FFD54F")

            # AZ columns
            for az_idx, (az_name, az_subs) in enumerate(sorted(az_map.items())):
                ax_col = vx + VPC_PAD + az_idx * (SUBNET_W + AZ_GAP)
                az_short = az_name.split("-")[-1] if az_name != "?" else "?"
                ax.text(ax_col + SUBNET_W / 2, 0.75, f"AZ {az_short}",
                        ha="center", fontsize=7, color="#80DEEA", style="italic")

                type_order = {"public": 0, "private": 1, "isolated": 2, "unknown": 3}
                az_subs_sorted = sorted(az_subs, key=lambda s: type_order.get(s.get("subnet_type", "unknown"), 3))

                for sub_idx, sub in enumerate(az_subs_sorted):
                    sid     = sub["resource_id"]
                    stype   = sub.get("subnet_type", "unknown")
                    sfill, sstroke = SUBNET_COLORS.get(stype, SUBNET_COLORS["unknown"])
                    sy = VPC_PAD + 0.5 + sub_idx * (SUBNET_H + SUBNET_GAP)

                    sub_patch = FancyBboxPatch(
                        (ax_col, sy), SUBNET_W, SUBNET_H,
                        boxstyle="round,pad=0.05",
                        facecolor=sfill, edgecolor=sstroke, linewidth=1.2, alpha=0.4,
                    )
                    ax.add_patch(sub_patch)

                    sub_label = (sub.get("tags", {}).get("Name") or sid)[:24]
                    sub_cidr  = sub.get("cidr_block", "")
                    ax.text(ax_col + SUBNET_W / 2, sy + SUBNET_H - 0.18,
                            f"{sub_label}  {sub_cidr}",
                            ha="center", va="top", fontsize=5.5, color="#333333")

                    # Resources inside subnet
                    resources: list[tuple[str, str]] = []
                    for nat in nat_by_subnet.get(sid, []):
                        resources.append((self._short_label(nat, 12), "#00838F"))
                    for lb in alb_by_subnet.get(sid, []):
                        resources.append((self._short_label(lb, 12), "#AD1457"))
                    for inst in ec2_by_subnet.get(sid, []):
                        resources.append((self._short_label(inst, 12), "#FF8F00"))
                    for ep in ep_by_subnet.get(sid, []):
                        svc = ep.get("service_name", "").split(".")[-1]
                        resources.append((svc[:12], "#4527A0"))

                    cols = RESOURCE_COLS
                    for ri, (rlabel, rcolor) in enumerate(resources):
                        col = ri % cols
                        row = ri // cols
                        rx = ax_col + SUBNET_PAD + col * ((SUBNET_W - SUBNET_PAD * 2) / cols)
                        ry = sy + 0.3 + row * 0.55
                        ax.plot(rx, ry, "o", markersize=8, color=rcolor, alpha=RESOURCE_ALPHA, zorder=4)
                        ax.text(rx, ry - 0.22, rlabel, ha="center", fontsize=4.5, color="#333333")

        # Legend
        legend_items = [
            mpatches.Patch(facecolor=SUBNET_COLORS["public"][0],   edgecolor=SUBNET_COLORS["public"][1],   label="Public subnet"),
            mpatches.Patch(facecolor=SUBNET_COLORS["private"][0],  edgecolor=SUBNET_COLORS["private"][1],  label="Private subnet"),
            mpatches.Patch(facecolor=SUBNET_COLORS["isolated"][0], edgecolor=SUBNET_COLORS["isolated"][1], label="Isolated subnet"),
            mpatches.Patch(color="#FF8F00", label="EC2"),
            mpatches.Patch(color="#AD1457", label="Load Balancer"),
            mpatches.Patch(color="#00838F", label="NAT Gateway"),
            mpatches.Patch(color="#4527A0", label="VPC Endpoint"),
            mpatches.Patch(color="#F57F17", label="EKS Cluster"),
        ]
        ax.legend(handles=legend_items, loc="lower right", fontsize=7, framealpha=0.6)
        ax.set_title(title, color="white", fontsize=13, pad=8)

        self.save(fig, output_path)
        logger.info("VPC diagram saved → %s", output_path)
