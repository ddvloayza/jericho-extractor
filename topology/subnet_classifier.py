from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from topology.route_analyzer import RouteAnalyzer, RouteTarget

logger = logging.getLogger(__name__)


class SubnetType(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    ISOLATED = "isolated"
    UNKNOWN = "unknown"


class SubnetClassifier:
    """
    Classifies subnets by inspecting their associated route table.

    public   — default route points to an IGW
    private  — default route points to a NAT gateway or TGW
    isolated — no default route to internet
    """

    def __init__(self) -> None:
        self._analyzer = RouteAnalyzer()

    def classify(
        self,
        subnet: dict[str, Any],
        route_tables: list[dict[str, Any]],
    ) -> SubnetType:
        subnet_id = subnet.get("resource_id", "")
        rt = self._find_route_table(subnet_id, route_tables)
        if rt is None:
            logger.debug("No route table found for subnet %s — marking unknown", subnet_id)
            return SubnetType.UNKNOWN

        default_route = self._analyzer.get_default_route(rt)
        if default_route is None:
            return SubnetType.ISOLATED

        if default_route.target_type == RouteTarget.IGW:
            return SubnetType.PUBLIC
        if default_route.target_type in (RouteTarget.NAT, RouteTarget.TGW):
            return SubnetType.PRIVATE

        return SubnetType.ISOLATED

    def classify_all(
        self,
        subnets: list[dict[str, Any]],
        route_tables: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return subnets with `subnet_type` field populated."""
        result = []
        for subnet in subnets:
            subnet_type = self.classify(subnet, route_tables)
            result.append({**subnet, "subnet_type": subnet_type.value})
        return result

    @staticmethod
    def _find_route_table(
        subnet_id: str,
        route_tables: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        # Prefer an explicit association
        for rt in route_tables:
            if subnet_id in rt.get("associated_subnet_ids", []):
                return rt
        # Fall back to the main route table of the same VPC
        # (caller must ensure route_tables are scoped to the same account/region)
        return None
