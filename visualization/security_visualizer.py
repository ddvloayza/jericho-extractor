from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from visualization.topology_renderer import TopologyRenderer

logger = logging.getLogger(__name__)

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyBboxPatch
    import numpy as np
    _MPL_AVAILABLE = True
except ImportError:
    _MPL_AVAILABLE = False


class SecurityVisualizer(TopologyRenderer):
    """Generates security exposure maps from SecurityAnalyzer output.

    Produces:
      - exposure_map.png   : heatmap of SGs by risk
      - public_resources.png: resources with public exposure
    """

    RISK_ORDER = ["critical", "high", "medium", "low", "info"]

    def render_exposure_map(
        self,
        sg_analyses: list[dict[str, Any]],
        output_path: Path,
        title: str = "Security Group Exposure Map",
    ) -> None:
        if not _MPL_AVAILABLE:
            logger.warning("matplotlib required for security visualization — skipping")
            return
        if not sg_analyses:
            logger.warning("No SG analyses — skipping exposure map")
            return

        # Filter to SGs that have attached resources or non-info risk
        visible = [a for a in sg_analyses if a.get("attached_count", 0) > 0 or a.get("overall_risk") != "info"]
        if not visible:
            visible = sg_analyses[:60]

        # Sort by risk then attached count
        risk_order = {r: i for i, r in enumerate(self.RISK_ORDER)}
        visible.sort(key=lambda a: (risk_order.get(str(a.get("overall_risk", "info")), 99), -a.get("attached_count", 0)))

        cols   = 8
        rows   = max(1, -(-len(visible) // cols))
        cell_w = 2.2
        cell_h = 1.4

        fig, ax = self._new_figure(w=cols * cell_w + 2, h=rows * cell_h + 3)
        fig.patch.set_facecolor("#0D1117")
        ax.set_facecolor("#0D1117")
        ax.set_xlim(-0.5, cols * cell_w)
        ax.set_ylim(-1, rows * cell_h + 1)
        ax.set_aspect("auto")

        for idx, sg in enumerate(visible):
            col = idx % cols
            row = idx // cols
            x   = col * cell_w
            y   = (rows - 1 - row) * cell_h

            risk  = str(sg.get("overall_risk", "info"))
            color = self.RISK_COLORS.get(risk, "#546E7A")
            name  = (sg.get("security_group_name") or sg.get("security_group_id", ""))[:18]
            count = sg.get("attached_count", 0)
            flags = sg.get("exposure_flags", [])

            patch = FancyBboxPatch(
                (x + 0.05, y + 0.05), cell_w - 0.15, cell_h - 0.15,
                boxstyle="round,pad=0.05",
                facecolor=color, edgecolor="white", linewidth=0.5, alpha=0.75,
            )
            ax.add_patch(patch)

            ax.text(x + cell_w / 2, y + cell_h - 0.25, name,
                    ha="center", va="top", fontsize=6, color="white", fontweight="bold")
            ax.text(x + cell_w / 2, y + cell_h / 2, f"{count} resources",
                    ha="center", va="center", fontsize=5.5, color="#EEEEEE")

            flag_icons = {"ssh_public": "⚠SSH", "rdp_public": "⚠RDP",
                          "full_open_inbound": "⚠ALL", "http_public": "HTTP",
                          "https_public": "HTTPS", "unrestricted_egress": "→ALL"}
            flag_text = "  ".join(flag_icons[f] for f in flags if f in flag_icons)[:20]
            if flag_text:
                ax.text(x + cell_w / 2, y + 0.22, flag_text,
                        ha="center", va="bottom", fontsize=4.5, color="#FFCDD2")

        # Risk legend
        legend_items = [
            mpatches.Patch(color=self.RISK_COLORS[r], label=r.capitalize())
            for r in self.RISK_ORDER
        ]
        ax.legend(handles=legend_items, loc="lower right", fontsize=7,
                  framealpha=0.5, facecolor="#1A1A2E", labelcolor="white")

        ax.set_title(title, color="white", fontsize=13, pad=10)
        ax.axis("off")

        self.save(fig, output_path)
        logger.info("Security exposure map saved → %s", output_path)

    def render_public_resources(
        self,
        sg_analyses: list[dict[str, Any]],
        all_resources: list[dict[str, Any]],
        output_path: Path,
        title: str = "Publicly Exposed Resources",
    ) -> None:
        if not _MPL_AVAILABLE:
            return

        # Collect critical/high SG IDs and their attached resources
        exposed_resource_ids: set[str] = set()
        critical_sg_ids: set[str] = set()
        for a in sg_analyses:
            if str(a.get("overall_risk")) in ("critical", "high"):
                critical_sg_ids.add(a["security_group_id"])
                exposed_resource_ids.update(a.get("attached_resources", []))

        # Also flag resources with ssh_public / rdp_public / full_open_inbound
        critical_flag_sgs: set[str] = set()
        for a in sg_analyses:
            flags = a.get("exposure_flags", [])
            if any(f in flags for f in ("ssh_public", "rdp_public", "full_open_inbound")):
                critical_flag_sgs.add(a["security_group_id"])

        resource_index = {r["resource_id"]: r for r in all_resources}
        exposed = [resource_index[rid] for rid in exposed_resource_ids if rid in resource_index]

        if not exposed:
            logger.info("No publicly exposed resources found — skipping public resources chart")
            return

        # Group by resource type
        by_type: dict[str, list[dict]] = {}
        for r in exposed:
            rtype = r.get("resource_type", "unknown").split("::")[-1]
            by_type.setdefault(rtype, []).append(r)

        type_list  = sorted(by_type.keys(), key=lambda t: -len(by_type[t]))
        cols       = 5
        cell_w, cell_h = 3.0, 0.8
        max_per_type   = 20

        total_rows = sum(-(-min(len(by_type[t]), max_per_type) // cols) + 1 for t in type_list)
        fig_h      = max(8, total_rows * cell_h + 2)

        fig, ax = self._new_figure(w=cols * cell_w + 2, h=fig_h)
        fig.patch.set_facecolor("#0D1117")
        ax.set_facecolor("#0D1117")
        ax.axis("off")

        cursor_y = fig_h - 1.5

        for rtype in type_list:
            resources = by_type[rtype][:max_per_type]
            color = self._resource_color(f"aws::ec2::{rtype}")
            ax.text(0.3, cursor_y, f"▶ {rtype.upper()} ({len(by_type[rtype])})",
                    fontsize=9, color="#FF8F00", fontweight="bold", va="top")
            cursor_y -= 0.5

            for idx, r in enumerate(resources):
                col  = idx % cols
                row  = idx // cols
                x    = col * cell_w + 0.3
                y    = cursor_y - row * cell_h - 0.1
                name = self._short_label(r, 28)
                sg_used = [sg for sg in r.get("security_group_ids", []) if sg in critical_sg_ids]
                is_critical = bool(set(r.get("security_group_ids", [])) & critical_flag_sgs)
                badge_color = "#D32F2F" if is_critical else "#F57C00"

                patch = FancyBboxPatch(
                    (x, y - cell_h + 0.1), cell_w - 0.2, cell_h - 0.15,
                    boxstyle="round,pad=0.04",
                    facecolor=badge_color, edgecolor=color, linewidth=0.8, alpha=0.65,
                )
                ax.add_patch(patch)
                ax.text(x + (cell_w - 0.2) / 2, y - cell_h / 2 + 0.1, name,
                        ha="center", va="center", fontsize=6, color="white")

            row_count = -(-len(resources) // cols)
            cursor_y -= row_count * cell_h + 0.5

        ax.set_title(title, color="white", fontsize=13)
        ax.set_xlim(0, cols * cell_w + 0.5)
        ax.set_ylim(cursor_y - 1, fig_h)

        self.save(fig, output_path)
        logger.info("Public resources chart saved → %s", output_path)

    def render_summary_bar(
        self,
        sg_analyses: list[dict[str, Any]],
        output_path: Path,
        title: str = "Security Posture Summary",
    ) -> None:
        if not _MPL_AVAILABLE:
            return
        counts = {r: 0 for r in self.RISK_ORDER}
        for a in sg_analyses:
            risk = str(a.get("overall_risk", "info"))
            counts[risk] = counts.get(risk, 0) + 1

        fig, ax = self._new_figure(w=10, h=5)
        fig.patch.set_facecolor("#0D1117")
        ax.set_facecolor("#161B22")

        labels = [r.capitalize() for r in self.RISK_ORDER]
        values = [counts[r] for r in self.RISK_ORDER]
        colors = [self.RISK_COLORS[r] for r in self.RISK_ORDER]

        bars = ax.bar(labels, values, color=colors, edgecolor="white", linewidth=0.5)
        for bar, val in zip(bars, values):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.2,
                        str(val), ha="center", fontsize=10, color="white", fontweight="bold")

        ax.set_title(title, color="white", fontsize=13)
        ax.set_ylabel("Security Groups", color="#AAAAAA")
        ax.tick_params(colors="white")
        ax.spines["bottom"].set_color("#444444")
        ax.spines["left"].set_color("#444444")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.yaxis.label.set_color("#AAAAAA")

        self.save(fig, output_path)
        logger.info("Security summary bar saved → %s", output_path)
