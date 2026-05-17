from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    node_id: str
    node_type: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    relation: str


@dataclass
class NetworkGraph:
    """
    In-memory graph representation of AWS network topology.
    Nodes = resources, Edges = relationships.
    Designed to be serialized later into a graph DB or visualization format.
    """

    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)

    def add_node(self, resource: dict[str, Any]) -> None:
        node_id = resource.get("resource_id", "")
        if not node_id:
            return
        self.nodes[node_id] = GraphNode(
            node_id=node_id,
            node_type=resource.get("resource_type", ""),
            label=resource.get("tags", {}).get("Name", node_id),
            properties={
                "account_id": resource.get("account_id", ""),
                "account_name": resource.get("account_name", ""),
                "region": resource.get("region", ""),
            },
        )

    def add_edges_from_relationships(self, resource: dict[str, Any]) -> None:
        source_id = resource.get("resource_id", "")
        for rel in resource.get("relationships", []):
            target_id = rel.get("resource_id", "")
            relation = rel.get("relation", "")
            if source_id and target_id:
                self.edges.append(
                    GraphEdge(source_id=source_id, target_id=target_id, relation=relation)
                )

    def build_from_inventory(self, all_resources: list[dict[str, Any]]) -> None:
        """Populate graph from a flat list of normalized resource dicts."""
        for resource in all_resources:
            self.add_node(resource)
            self.add_edges_from_relationships(resource)
        logger.info(
            "Graph built: %d nodes, %d edges", len(self.nodes), len(self.edges)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "id": n.node_id,
                    "type": n.node_type,
                    "label": n.label,
                    "properties": n.properties,
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "source": e.source_id,
                    "target": e.target_id,
                    "relation": e.relation,
                }
                for e in self.edges
            ],
        }
