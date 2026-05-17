from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import matplotlib
    matplotlib.use("Agg")          # non-interactive backend — works headless
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    _MPL_AVAILABLE = True
except ImportError:
    _MPL_AVAILABLE = False
    plt = None  # type: ignore[assignment]
    mpatches = None  # type: ignore[assignment]


class TopologyRenderer:
    """Base class for all topology visualizers.

    Subclasses call self._fig / self._ax to draw, then call save().
    """

    MPL_AVAILABLE = _MPL_AVAILABLE

    # Risk color palette (shared across visualizers)
    RISK_COLORS = {
        "critical": "#D32F2F",
        "high":     "#F57C00",
        "medium":   "#FBC02D",
        "low":      "#388E3C",
        "info":     "#1565C0",
        "unknown":  "#757575",
    }

    # Resource type colors
    RESOURCE_COLORS = {
        "aws::ec2::vpc":               "#1976D2",
        "aws::ec2::subnet":            "#43A047",
        "aws::ec2::instance":          "#FF8F00",
        "aws::ec2::internet_gateway":  "#6A1B9A",
        "aws::ec2::nat_gateway":       "#00838F",
        "aws::ec2::transit_gateway":   "#E64A19",
        "aws::ec2::security_group":    "#C62828",
        "aws::ec2::network_interface": "#78909C",
        "aws::ec2::vpc_endpoint":      "#4527A0",
        "aws::elasticloadbalancing::loadbalancer": "#AD1457",
        "aws::eks::cluster":           "#F57F17",
        "default":                     "#546E7A",
    }

    def _resource_color(self, resource_type: str) -> str:
        return self.RESOURCE_COLORS.get(resource_type, self.RESOURCE_COLORS["default"])

    def _new_figure(self, w: float = 20, h: float = 14) -> tuple[Any, Any]:
        if not _MPL_AVAILABLE:
            raise ImportError("matplotlib is required for visualization. pip install matplotlib")
        fig, ax = plt.subplots(figsize=(w, h))
        ax.set_aspect("equal")
        ax.axis("off")
        return fig, ax

    def save(self, fig: Any, output_path: Path, dpi: int = 150) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)

    def _short_label(self, resource: dict[str, Any], max_len: int = 22) -> str:
        name = resource.get("tags", {}).get("Name") or resource.get("resource_name") or resource.get("resource_id", "")
        return name if len(name) <= max_len else name[:max_len - 1] + "…"
