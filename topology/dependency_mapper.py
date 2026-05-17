from __future__ import annotations

import logging
from typing import Any

from topology.route_analyzer import RouteAnalyzer, RouteTarget

logger = logging.getLogger(__name__)


class DependencyMapper:
    """
    Builds EC2 → subnet → route_table → gateway chains and enriches
    resource records with cross-resource relationship edges.
    """

    def __init__(self) -> None:
        self._analyzer = RouteAnalyzer()

    def build_ec2_chains(
        self,
        instances: list[dict[str, Any]],
        subnets: list[dict[str, Any]],
        route_tables: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Return a list of dependency chain records, one per EC2 instance.
        Each record traces: instance → subnet → route_table → gateway.
        """
        subnet_index = {s["resource_id"]: s for s in subnets}
        rt_by_subnet = self._index_rt_by_subnet(route_tables)
        main_rt_by_vpc = self._index_main_rt_by_vpc(route_tables)

        chains = []
        for instance in instances:
            instance_id = instance.get("resource_id", "")
            subnet_id = instance.get("subnet_id", "")
            vpc_id = instance.get("vpc_id", "")

            subnet = subnet_index.get(subnet_id)
            rt = rt_by_subnet.get(subnet_id) or main_rt_by_vpc.get(vpc_id)
            default_route = self._analyzer.get_default_route(rt) if rt else None

            chains.append(
                {
                    "instance_id": instance_id,
                    "instance_name": instance.get("tags", {}).get("Name", ""),
                    "subnet_id": subnet_id,
                    "subnet_type": subnet.get("subnet_type", "unknown") if subnet else "unknown",
                    "vpc_id": vpc_id,
                    "route_table_id": rt.get("resource_id", "") if rt else "",
                    "default_route_target_type": default_route.target_type.value
                    if default_route
                    else "",
                    "default_route_target_id": default_route.target_id
                    if default_route
                    else "",
                    "internet_accessible": default_route is not None
                    and default_route.target_type
                    in (RouteTarget.IGW, RouteTarget.NAT, RouteTarget.TGW),
                }
            )
        return chains

    @staticmethod
    def _index_rt_by_subnet(
        route_tables: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for rt in route_tables:
            for subnet_id in rt.get("associated_subnet_ids", []):
                index[subnet_id] = rt
        return index

    @staticmethod
    def _index_main_rt_by_vpc(
        route_tables: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for rt in route_tables:
            if rt.get("is_main") and rt.get("vpc_id"):
                index[rt["vpc_id"]] = rt
        return index
