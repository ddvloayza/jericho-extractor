from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from visualization.topology_renderer import TopologyRenderer

logger = logging.getLogger(__name__)

try:
    import networkx as nx
    _NX_AVAILABLE = True
except ImportError:
    _NX_AVAILABLE = False

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    _MPL_AVAILABLE = True
except ImportError:
    _MPL_AVAILABLE = False


class GraphVisualizer(TopologyRenderer):
    """Renders the infrastructure dependency graph as PNG/SVG.

    Uses networkx spring_layout for positioning and matplotlib for drawing.
    Large graphs are automatically filtered to the most connected nodes.
    """

    MAX_NODES = 120   # truncate for readability

    def render(
        self,
        graph: Any,  # NetworkGraph instance
        output_path: Path,
        title: str = "Infrastructure Dependency Graph",
        highlight_internet_facing: bool = True,
    ) -> None:
        if not _MPL_AVAILABLE or not _NX_AVAILABLE:
            logger.warning("matplotlib/networkx required for graph visualization — skipping")
            return
        if graph.graph is None:
            logger.warning("Graph not built (networkx unavailable) — skipping")
            return

        G = graph.graph
        if G.number_of_nodes() == 0:
            logger.warning("Graph has no nodes — skipping visualization")
            return

        # Reduce graph for readability: keep nodes with most connections
        if G.number_of_nodes() > self.MAX_NODES:
            top_nodes = sorted(G.nodes, key=lambda n: G.degree(n), reverse=True)[:self.MAX_NODES]
            G = G.subgraph(top_nodes).copy()

        internet_facing = {r["resource_id"] for r in graph.get_internet_facing()}

        # Node colors by type
        node_colors = []
        node_sizes  = []
        for node in G.nodes:
            rtype = G.nodes[node].get("resource_type", "")
            color = self._resource_color(rtype)
            node_colors.append("#FF1744" if node in internet_facing else color)
            degree = G.degree(node)
            node_sizes.append(max(200, min(1200, degree * 80)))

        # Labels: short names only
        labels = {}
        for node in G.nodes:
            r = graph._resource_index.get(node, {})
            labels[node] = self._short_label(r, max_len=18)

        # Layout
        pos = nx.spring_layout(G, k=2.5, iterations=50, seed=42)

        fig, ax = self._new_figure(w=24, h=18)
        fig.patch.set_facecolor("#1A1A2E")
        ax.set_facecolor("#1A1A2E")

        # Draw edges
        nx.draw_networkx_edges(
            G, pos, ax=ax,
            edge_color="#444466",
            alpha=0.4,
            arrows=True,
            arrowsize=8,
            width=0.8,
            connectionstyle="arc3,rad=0.1",
        )

        # Draw nodes
        nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors, node_size=node_sizes, alpha=0.9)

        # Draw labels
        nx.draw_networkx_labels(G, pos, labels=labels, ax=ax, font_size=6, font_color="#EEEEEE")

        # Legend
        legend_items = [
            mpatches.Patch(color=c, label=t.split("::")[-1])
            for t, c in self.RESOURCE_COLORS.items() if t != "default"
        ]
        if highlight_internet_facing:
            legend_items.append(mpatches.Patch(color="#FF1744", label="internet-facing"))
        ax.legend(handles=legend_items, loc="upper left", fontsize=7,
                  framealpha=0.3, facecolor="#2A2A4E", labelcolor="white")

        ax.set_title(title, color="white", fontsize=14, pad=12)

        self.save(fig, output_path)
        logger.info("Graph visualization saved → %s", output_path)

    def render_subgraph(
        self,
        graph: Any,
        root_resource_id: str,
        depth: int = 3,
        output_path: Path | None = None,
        title: str | None = None,
    ) -> None:
        """Render a focused subgraph around a specific resource."""
        if not _MPL_AVAILABLE or not _NX_AVAILABLE or graph.graph is None:
            return
        G = graph.graph
        if root_resource_id not in G:
            logger.warning("Resource %s not in graph", root_resource_id)
            return

        # Ego graph: nodes within `depth` hops
        ego = nx.ego_graph(G, root_resource_id, radius=depth, undirected=True)

        node_colors = []
        for node in ego.nodes:
            if node == root_resource_id:
                node_colors.append("#FF1744")
            else:
                rtype = G.nodes[node].get("resource_type", "")
                node_colors.append(self._resource_color(rtype))

        labels = {n: self._short_label(graph._resource_index.get(n, {}), 20) for n in ego.nodes}
        pos = nx.spring_layout(ego, k=3, seed=42)

        out = output_path or Path(f"subgraph_{root_resource_id[:12]}.png")
        ttl = title or f"Subgraph: {root_resource_id[:30]}"

        fig, ax = self._new_figure(w=16, h=12)
        fig.patch.set_facecolor("#1A1A2E")
        ax.set_facecolor("#1A1A2E")
        nx.draw_networkx_edges(ego, pos, ax=ax, edge_color="#555577", alpha=0.5, arrows=True, arrowsize=10)
        nx.draw_networkx_nodes(ego, pos, ax=ax, node_color=node_colors, node_size=600, alpha=0.9)
        nx.draw_networkx_labels(ego, pos, labels=labels, ax=ax, font_size=7, font_color="#EEEEEE")
        ax.set_title(ttl, color="white", fontsize=12)

        self.save(fig, out)
        logger.info("Subgraph saved → %s", out)
