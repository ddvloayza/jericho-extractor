from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

try:
    import networkx as nx
    _NX_AVAILABLE = True
except ImportError:
    _NX_AVAILABLE = False
    nx = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from topology.relationship_engine import Edge

logger = logging.getLogger(__name__)


class NetworkGraph:
    """Navigable infrastructure graph backed by networkx.DiGraph.

    Nodes = AWS resources (resource_id as key).
    Edges = typed relationships between resources.

    When networkx is not installed, basic serialization still works
    but graph traversal queries return empty results.
    """

    def __init__(self) -> None:
        if _NX_AVAILABLE:
            self.graph: Any = nx.DiGraph()
        else:
            self.graph = None
            logger.warning("networkx not installed — graph traversal queries unavailable")
        self._resource_index: dict[str, dict[str, Any]] = {}

    # ── Population ────────────────────────────────────────────────────────────

    def add_node(self, resource: dict[str, Any]) -> None:
        rid = resource.get("resource_id", "")
        if not rid:
            return
        self._resource_index[rid] = resource
        if self.graph is not None:
            self.graph.add_node(rid, **{
                "resource_type": resource.get("resource_type", ""),
                "resource_name": resource.get("resource_name", ""),
                "account_id":    resource.get("account_id", ""),
                "region":        resource.get("region", ""),
                "vpc_id":        resource.get("vpc_id", ""),
                "subnet_type":   resource.get("subnet_type", ""),
            })

    def add_edge_raw(self, source_id: str, target_id: str, relation: str, **metadata: Any) -> None:
        if self.graph is not None and source_id in self.graph and target_id in self.graph:
            self.graph.add_edge(source_id, target_id, relation=relation, **metadata)

    def build_from_inventory(self, resources: list[dict[str, Any]]) -> None:
        for r in resources:
            self.add_node(r)
        for r in resources:
            for rel in r.get("relationships", []):
                self.add_edge_raw(
                    r["resource_id"],
                    rel.get("target_id", ""),
                    rel.get("relation", ""),
                )

    def build_from_edges(self, edges: list[Edge]) -> None:
        """Ingest edges produced by RelationshipEngine."""
        added = 0
        for edge in edges:
            if self.graph is not None and edge.source_id in self.graph and edge.target_id in self.graph:
                self.graph.add_edge(
                    edge.source_id, edge.target_id,
                    relation=edge.relation,
                    **edge.metadata,
                )
                added += 1
        logger.info("NetworkGraph: added %d/%d edges from RelationshipEngine", added, len(edges))

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_internet_facing(self) -> list[dict[str, Any]]:
        """Resources reachable from an Internet Gateway."""
        if self.graph is None:
            return []
        igw_nodes = [n for n in self.graph.nodes if self._type(n).endswith("internet_gateway")]
        reachable: set[str] = set()
        for igw in igw_nodes:
            reachable.update(nx.descendants(self.graph, igw))
        return [self._resource_index[n] for n in reachable if n in self._resource_index]

    def get_resources_in_subnet(self, subnet_id: str) -> list[dict[str, Any]]:
        if self.graph is None or subnet_id not in self.graph:
            return []
        return [
            self._resource_index[n]
            for n in self.graph.predecessors(subnet_id)
            if self._edge_relation(n, subnet_id) in {"deployed_in_subnet", "in_subnet", "uses_subnet"}
            and n in self._resource_index
        ]

    def get_resources_using_sg(self, sg_id: str) -> list[dict[str, Any]]:
        if self.graph is None or sg_id not in self.graph:
            return []
        return [
            self._resource_index[n]
            for n in self.graph.predecessors(sg_id)
            if self._edge_relation(n, sg_id) == "protected_by_sg"
            and n in self._resource_index
        ]

    def get_blast_radius(self, resource_id: str) -> dict[str, Any]:
        """Everything that depends on this resource (all graph ancestors)."""
        if self.graph is None or resource_id not in self.graph:
            return {"resource_id": resource_id, "dependent_count": 0, "dependents": []}
        ancestors = list(nx.ancestors(self.graph, resource_id))
        return {
            "resource_id":     resource_id,
            "resource_type":   self._type(resource_id),
            "dependent_count": len(ancestors),
            "dependents": [
                {"resource_id": d, "resource_type": self._type(d)}
                for d in ancestors if d in self._resource_index
            ],
        }

    def get_dependency_chain(self, resource_id: str) -> list[list[dict[str, Any]]]:
        """Shortest paths from this resource toward any Internet Gateway."""
        if self.graph is None or resource_id not in self.graph:
            return []
        igw_nodes = [n for n in self.graph.nodes if self._type(n).endswith("internet_gateway")]
        chains = []
        for igw in igw_nodes:
            try:
                path = nx.shortest_path(self.graph, resource_id, igw)
                chains.append([{"resource_id": n, "resource_type": self._type(n)} for n in path])
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                pass
        return chains

    def get_nat_dependents(self) -> list[dict[str, Any]]:
        """Resources whose traffic flows through a NAT Gateway."""
        if self.graph is None:
            return []
        nat_nodes = [n for n in self.graph.nodes if self._type(n).endswith("nat_gateway")]
        dependents: set[str] = set()
        for nat in nat_nodes:
            dependents.update(nx.ancestors(self.graph, nat))
        return [self._resource_index[n] for n in dependents if n in self._resource_index]

    def get_tgw_workloads(self) -> dict[str, list[dict[str, Any]]]:
        """Per-TGW: all resources reachable through that gateway."""
        if self.graph is None:
            return {}
        result: dict[str, list[dict[str, Any]]] = {}
        for tgw in [n for n in self.graph.nodes if self._type(n).endswith("transit_gateway")]:
            ancestors = list(nx.ancestors(self.graph, tgw))
            result[tgw] = [self._resource_index[n] for n in ancestors if n in self._resource_index]
        return result

    def get_public_subnets(self) -> list[dict[str, Any]]:
        return [r for r in self._resource_index.values()
                if r.get("resource_type", "").endswith("subnet") and r.get("subnet_type") == "public"]

    def get_private_subnets(self) -> list[dict[str, Any]]:
        return [r for r in self._resource_index.values()
                if r.get("resource_type", "").endswith("subnet") and r.get("subnet_type") == "private"]

    def get_isolated_subnets(self) -> list[dict[str, Any]]:
        return [r for r in self._resource_index.values()
                if r.get("resource_type", "").endswith("subnet") and r.get("subnet_type") == "isolated"]

    def get_route_tables_for_subnet(self, subnet_id: str) -> list[dict[str, Any]]:
        if self.graph is None or subnet_id not in self.graph:
            return []
        return [
            self._resource_index[n]
            for n in self.graph.successors(subnet_id)
            if self._type(n).endswith("route_table") and n in self._resource_index
        ]

    def get_what_depends_on(self, resource_id: str) -> list[dict[str, Any]]:
        """Direct predecessors — resources that directly reference this one."""
        if self.graph is None or resource_id not in self.graph:
            return []
        return [self._resource_index[n] for n in self.graph.predecessors(resource_id) if n in self._resource_index]

    def get_what_this_uses(self, resource_id: str) -> list[dict[str, Any]]:
        """Direct successors — resources this one directly depends on."""
        if self.graph is None or resource_id not in self.graph:
            return []
        return [self._resource_index[n] for n in self.graph.successors(resource_id) if n in self._resource_index]

    def find_resources_by_type(self, resource_type: str) -> list[dict[str, Any]]:
        return [r for r in self._resource_index.values() if r.get("resource_type") == resource_type]

    def find_resources_by_tag(self, key: str, value: str) -> list[dict[str, Any]]:
        return [r for r in self._resource_index.values() if r.get("tags", {}).get(key) == value]

    # ── Summary & serialization ───────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        base: dict[str, Any] = {
            "node_count":           len(self._resource_index),
            "public_subnet_count":  len(self.get_public_subnets()),
            "private_subnet_count": len(self.get_private_subnets()),
        }
        if self.graph is not None:
            base.update({
                "edge_count":            self.graph.number_of_edges(),
                "connected_components":  nx.number_weakly_connected_components(self.graph),
                "internet_facing_count": len(self.get_internet_facing()),
            })
        return base

    def to_dict(self) -> dict[str, Any]:
        if self.graph is None:
            return {"nodes": list(self._resource_index.values()), "edges": [], "summary": self.summary()}
        return {
            "nodes": [{"id": n, **dict(self.graph.nodes[n])} for n in self.graph.nodes],
            "edges": [{"source": u, "target": v, **dict(d)} for u, v, d in self.graph.edges(data=True)],
            "summary": self.summary(),
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _type(self, node_id: str) -> str:
        return (self.graph.nodes.get(node_id) or {}).get("resource_type", "") if self.graph is not None else ""

    def _edge_relation(self, source: str, target: str) -> str:
        if self.graph is None:
            return ""
        return ((self.graph.get_edge_data(source, target)) or {}).get("relation", "")
