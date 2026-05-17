from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Edge:
    source_id: str
    source_type: str
    target_id: str
    target_type: str
    relation: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "target_id": self.target_id,
            "target_type": self.target_type,
            "relation": self.relation,
            "metadata": self.metadata,
        }


class RelationshipEngine:
    """Traverses all collected resources and derives explicit edges between them.

    Each build_* method handles one resource category. Edges are unidirectional
    (source → target) but queries on the graph can traverse in either direction.
    """

    def build_all(self, inventory: dict[str, list[dict[str, Any]]]) -> list[Edge]:
        edges: list[Edge] = []
        edges.extend(self._ec2(inventory))
        edges.extend(self._enis(inventory))
        edges.extend(self._subnets(inventory))
        edges.extend(self._route_tables(inventory))
        edges.extend(self._gateways(inventory))
        edges.extend(self._nat_gateways(inventory))
        edges.extend(self._tgw_attachments(inventory))
        edges.extend(self._vpc_peerings(inventory))
        edges.extend(self._vpc_endpoints(inventory))
        edges.extend(self._load_balancers(inventory))
        edges.extend(self._target_groups(inventory))
        edges.extend(self._eks(inventory))
        edges.extend(self._sg_references(inventory))
        logger.info("RelationshipEngine: built %d edges total", len(edges))
        return edges

    # ── EC2 ───────────────────────────────────────────────────────────────────

    def _ec2(self, inv: dict) -> list[Edge]:
        edges = []
        for inst in inv.get("ec2", []):
            if inst.get("state") == "terminated":
                continue
            iid = inst["resource_id"]
            rt = "aws::ec2::instance"
            if inst.get("subnet_id"):
                edges.append(Edge(iid, rt, inst["subnet_id"], "aws::ec2::subnet", "deployed_in_subnet"))
            if inst.get("vpc_id"):
                edges.append(Edge(iid, rt, inst["vpc_id"], "aws::ec2::vpc", "deployed_in_vpc"))
            for sg in inst.get("security_group_ids", []):
                edges.append(Edge(iid, rt, sg, "aws::ec2::security_group", "protected_by_sg"))
        return edges

    # ── ENIs ─────────────────────────────────────────────────────────────────

    def _enis(self, inv: dict) -> list[Edge]:
        edges = []
        for eni in inv.get("network_interfaces", []):
            eid = eni["resource_id"]
            rt = "aws::ec2::network_interface"
            if eni.get("subnet_id"):
                edges.append(Edge(eid, rt, eni["subnet_id"], "aws::ec2::subnet", "in_subnet"))
            if eni.get("vpc_id"):
                edges.append(Edge(eid, rt, eni["vpc_id"], "aws::ec2::vpc", "in_vpc"))
            for sg in eni.get("security_group_ids", []):
                edges.append(Edge(eid, rt, sg, "aws::ec2::security_group", "protected_by_sg"))
            instance_id = (eni.get("attachment") or {}).get("instance_id", "")
            if instance_id:
                edges.append(Edge(eid, rt, instance_id, "aws::ec2::instance", "attached_to_instance"))
        return edges

    # ── Subnets ───────────────────────────────────────────────────────────────

    def _subnets(self, inv: dict) -> list[Edge]:
        edges = []
        for subnet in inv.get("subnets", []):
            sid = subnet["resource_id"]
            if subnet.get("vpc_id"):
                edges.append(Edge(sid, "aws::ec2::subnet", subnet["vpc_id"], "aws::ec2::vpc", "belongs_to_vpc"))
        return edges

    # ── Route tables ─────────────────────────────────────────────────────────

    def _route_tables(self, inv: dict) -> list[Edge]:
        edges = []
        for rt in inv.get("route_tables", []):
            rtid = rt["resource_id"]
            rtype = "aws::ec2::route_table"
            if rt.get("vpc_id"):
                edges.append(Edge(rtid, rtype, rt["vpc_id"], "aws::ec2::vpc", "belongs_to_vpc"))
            # subnet ↔ route table via associations
            for assoc in rt.get("associations", []):
                sid = assoc.get("subnet_id", "")
                if sid:
                    edges.append(Edge(sid, "aws::ec2::subnet", rtid, rtype, "associated_with_rt"))
            # route entries → gateways
            for route in rt.get("routes", []):
                dest = route.get("destination_cidr_block") or route.get("destination_ipv6_cidr_block", "")
                meta = {"destination": dest}
                gw_id = route.get("gateway_id", "")
                nat_id = route.get("nat_gateway_id", "")
                tgw_id = route.get("transit_gateway_id", "")
                ep_id = route.get("vpc_endpoint_id", "")
                pcx_id = route.get("vpc_peering_connection_id", "")
                if gw_id and gw_id.startswith("igw-"):
                    edges.append(Edge(rtid, rtype, gw_id, "aws::ec2::internet_gateway", "routes_to_igw", meta))
                if nat_id:
                    edges.append(Edge(rtid, rtype, nat_id, "aws::ec2::nat_gateway", "routes_to_nat", meta))
                if tgw_id:
                    edges.append(Edge(rtid, rtype, tgw_id, "aws::ec2::transit_gateway", "routes_to_tgw", meta))
                if ep_id:
                    edges.append(Edge(rtid, rtype, ep_id, "aws::ec2::vpc_endpoint", "routes_to_endpoint", meta))
                if pcx_id:
                    edges.append(Edge(rtid, rtype, pcx_id, "aws::ec2::vpc_peering", "routes_to_peering", meta))
        return edges

    # ── IGWs ─────────────────────────────────────────────────────────────────

    def _gateways(self, inv: dict) -> list[Edge]:
        edges = []
        for igw in inv.get("internet_gateways", []):
            igw_id = igw["resource_id"]
            for vpc_id in igw.get("attached_vpc_ids", []):
                edges.append(Edge(igw_id, "aws::ec2::internet_gateway", vpc_id, "aws::ec2::vpc", "attached_to_vpc"))
        return edges

    # ── NAT gateways ─────────────────────────────────────────────────────────

    def _nat_gateways(self, inv: dict) -> list[Edge]:
        edges = []
        for nat in inv.get("nat_gateways", []):
            nid = nat["resource_id"]
            rt = "aws::ec2::nat_gateway"
            if nat.get("subnet_id"):
                edges.append(Edge(nid, rt, nat["subnet_id"], "aws::ec2::subnet", "deployed_in_subnet"))
            if nat.get("vpc_id"):
                edges.append(Edge(nid, rt, nat["vpc_id"], "aws::ec2::vpc", "deployed_in_vpc"))
        return edges

    # ── TGW attachments ───────────────────────────────────────────────────────

    def _tgw_attachments(self, inv: dict) -> list[Edge]:
        edges = []
        for att in inv.get("transit_gateway_attachments", []):
            tgw_id = att.get("transit_gateway_id", "")
            vpc_id = att.get("resource_id_ref", "")
            if tgw_id and vpc_id:
                edges.append(Edge(
                    vpc_id, "aws::ec2::vpc",
                    tgw_id, "aws::ec2::transit_gateway",
                    "connected_via_tgw",
                    {"attachment_id": att["resource_id"]},
                ))
        return edges

    # ── VPC peerings ─────────────────────────────────────────────────────────

    def _vpc_peerings(self, inv: dict) -> list[Edge]:
        edges = []
        for pcx in inv.get("vpc_peerings", []):
            req = pcx.get("requester_vpc_id", "")
            acc = pcx.get("accepter_vpc_id", "")
            if req and acc:
                edges.append(Edge(req, "aws::ec2::vpc", acc, "aws::ec2::vpc", "peered_with", {"peering_id": pcx["resource_id"]}))
        return edges

    # ── VPC endpoints ─────────────────────────────────────────────────────────

    def _vpc_endpoints(self, inv: dict) -> list[Edge]:
        edges = []
        for ep in inv.get("vpc_endpoints", []):
            eid = ep["resource_id"]
            rt = "aws::ec2::vpc_endpoint"
            if ep.get("vpc_id"):
                edges.append(Edge(eid, rt, ep["vpc_id"], "aws::ec2::vpc", "in_vpc"))
            for sid in ep.get("associated_subnet_ids", []):
                edges.append(Edge(eid, rt, sid, "aws::ec2::subnet", "deployed_in_subnet"))
        return edges

    # ── Load balancers ────────────────────────────────────────────────────────

    def _load_balancers(self, inv: dict) -> list[Edge]:
        edges = []
        for lb in inv.get("load_balancers", []):
            lid = lb["resource_id"]
            rt = "aws::elasticloadbalancing::loadbalancer"
            if lb.get("vpc_id"):
                edges.append(Edge(lid, rt, lb["vpc_id"], "aws::ec2::vpc", "deployed_in_vpc"))
            for az in lb.get("availability_zones", []):
                sid = az.get("SubnetId", "")
                if sid:
                    edges.append(Edge(lid, rt, sid, "aws::ec2::subnet", "deployed_in_subnet"))
            for sg in lb.get("security_group_ids", []):
                edges.append(Edge(lid, rt, sg, "aws::ec2::security_group", "protected_by_sg"))
        return edges

    # ── Target groups ─────────────────────────────────────────────────────────

    def _target_groups(self, inv: dict) -> list[Edge]:
        edges = []
        for tg in inv.get("target_groups", []):
            tgid = tg["resource_id"]
            tgrt = "aws::elasticloadbalancing::targetgroup"
            for lb_arn in tg.get("load_balancer_arns", []):
                edges.append(Edge(lb_arn, "aws::elasticloadbalancing::loadbalancer", tgid, tgrt, "routes_to_tg"))
            for target in tg.get("targets", []):
                tid = target.get("id", "")
                if tid:
                    edges.append(Edge(tgid, tgrt, tid, "aws::ec2::instance", "forwards_to"))
        return edges

    # ── EKS ──────────────────────────────────────────────────────────────────

    def _eks(self, inv: dict) -> list[Edge]:
        edges = []
        for r in inv.get("eks", []):
            rid = r["resource_id"]
            rtype = r.get("resource_type", "")
            if rtype == "aws::eks::cluster":
                if r.get("vpc_id"):
                    edges.append(Edge(rid, rtype, r["vpc_id"], "aws::ec2::vpc", "deployed_in_vpc"))
                for sid in r.get("subnet_ids", []):
                    edges.append(Edge(rid, rtype, sid, "aws::ec2::subnet", "uses_subnet"))
                for sg in r.get("security_group_ids", []):
                    edges.append(Edge(rid, rtype, sg, "aws::ec2::security_group", "protected_by_sg"))
            elif rtype == "aws::eks::nodegroup":
                if r.get("cluster_arn"):
                    edges.append(Edge(rid, rtype, r["cluster_arn"], "aws::eks::cluster", "belongs_to_cluster"))
                for sid in r.get("subnet_ids", []):
                    edges.append(Edge(rid, rtype, sid, "aws::ec2::subnet", "deployed_in_subnet"))
        return edges

    # ── SG → SG references ────────────────────────────────────────────────────

    def _sg_references(self, inv: dict) -> list[Edge]:
        edges = []
        for sg in inv.get("security_groups", []):
            sgid = sg["resource_id"]
            for rule in sg.get("inbound_rules", []) + sg.get("outbound_rules", []):
                for ref in rule.get("referenced_group_ids", []):
                    if ref:
                        edges.append(Edge(sgid, "aws::ec2::security_group", ref, "aws::ec2::security_group", "references_sg"))
        return edges
