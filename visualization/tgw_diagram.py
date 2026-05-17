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
    _MPL_AVAILABLE = True
except ImportError:
    _MPL_AVAILABLE = False


class TGWDiagram(TopologyRenderer):
    """Renders a Transit Gateway topology: TGW hub and spoke VPC attachments."""

    def render(
        self,
        inventory: dict[str, list[dict[str, Any]]],
        output_path: Path,
        title: str = "Transit Gateway Topology",
    ) -> None:
        if not _MPL_AVAILABLE:
            logger.warning("matplotlib required for TGW diagram — skipping")
            return

        tgws         = inventory.get("transit_gateways", [])
        attachments  = inventory.get("transit_gateway_attachments", [])
        vpcs         = {v["resource_id"]: v for v in inventory.get("vpcs", [])}

        if not tgws and not attachments:
            logger.info("No TGW resources — skipping TGW diagram")
            return

        # Group attachments by TGW
        att_by_tgw: dict[str, list[dict]] = {}
        for att in attachments:
            tgw_id = att.get("transit_gateway_id", "__unknown__")
            att_by_tgw.setdefault(tgw_id, []).append(att)

        all_tgw_ids = list({t["resource_id"] for t in tgws} | set(att_by_tgw.keys()))

        fig, ax = self._new_figure(w=16, h=10)
        fig.patch.set_facecolor("#0D1117")
        ax.set_facecolor("#0D1117")
        ax.set_aspect("equal")
        ax.axis("off")

        hub_radius   = 0.8
        spoke_radius = 3.5

        for tgw_idx, tgw_id in enumerate(all_tgw_ids):
            cx = tgw_idx * 10
            cy = 5

            # TGW hub circle
            hub = plt.Circle((cx, cy), hub_radius, color="#E64A19", zorder=5, alpha=0.9)
            ax.add_patch(hub)
            tgw_name = (vpcs.get(tgw_id, {}).get("tags", {}).get("Name") or tgw_id)[:20]
            ax.text(cx, cy, "TGW", ha="center", va="center", fontsize=9,
                    color="white", fontweight="bold", zorder=6)
            ax.text(cx, cy - hub_radius - 0.3, tgw_id[:20],
                    ha="center", fontsize=6, color="#FF8A65")

            spokes = att_by_tgw.get(tgw_id, [])
            n      = len(spokes)
            for i, att in enumerate(spokes):
                angle = 2 * math.pi * i / max(n, 1) - math.pi / 2
                sx = cx + spoke_radius * math.cos(angle)
                sy = cy + spoke_radius * math.sin(angle)

                vpc_id   = att.get("resource_id_ref", "")
                vpc      = vpcs.get(vpc_id, {})
                vpc_name = (vpc.get("tags", {}).get("Name") or vpc_id or "VPC")[:18]
                vpc_cidr = vpc.get("cidr_block", "")
                att_type = att.get("attachment_type", "vpc")

                # Spoke node
                node = plt.Circle((sx, sy), 0.6, color="#1565C0", zorder=4, alpha=0.85)
                ax.add_patch(node)
                ax.text(sx, sy, vpc_name[:12], ha="center", va="center",
                        fontsize=6, color="white", fontweight="bold", zorder=5)
                if vpc_cidr:
                    ax.text(sx, sy - 0.85, vpc_cidr,
                            ha="center", fontsize=5.5, color="#90CAF9")

                # Spoke line
                ax.annotate(
                    "", xy=(cx + hub_radius * math.cos(angle), cy + hub_radius * math.sin(angle)),
                    xytext=(sx - 0.6 * math.cos(angle), sy - 0.6 * math.sin(angle)),
                    arrowprops=dict(arrowstyle="<->", color="#FF8A65", lw=1.5),
                )
                ax.text(
                    (cx + sx) / 2 + 0.1, (cy + sy) / 2 + 0.1,
                    att_type[:8], fontsize=5, color="#FFCCBC",
                )

        ax.set_xlim(-5, len(all_tgw_ids) * 10 + 5)
        ax.set_ylim(0, 10)
        ax.set_title(title, color="white", fontsize=13, pad=8)

        self.save(fig, output_path)
        logger.info("TGW diagram saved → %s", output_path)
