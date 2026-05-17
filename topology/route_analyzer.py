from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CIDR = "0.0.0.0/0"
DEFAULT_IPV6_CIDR = "::/0"


class RouteTarget(str, Enum):
    IGW = "igw"
    NAT = "nat"
    TGW = "tgw"
    VPC_PEERING = "pcx"
    VPC_ENDPOINT = "vpce"
    INSTANCE = "instance"
    NETWORK_INTERFACE = "eni"
    LOCAL = "local"
    UNKNOWN = "unknown"


@dataclass
class DefaultRouteInfo:
    target_type: RouteTarget
    target_id: str
    destination: str


class RouteAnalyzer:
    """Analyzes routes in a normalized route table record."""

    def get_default_route(self, route_table: dict[str, Any]) -> DefaultRouteInfo | None:
        """Return info about the default (0.0.0.0/0) route, if any."""
        for route in route_table.get("routes", []):
            dest = route.get("destination_cidr", "") or route.get(
                "destination_ipv6_cidr", ""
            )
            if dest not in (DEFAULT_CIDR, DEFAULT_IPV6_CIDR):
                continue
            return DefaultRouteInfo(
                target_type=self._resolve_target_type(route),
                target_id=self._resolve_target_id(route),
                destination=dest,
            )
        return None

    def get_all_routes(self, route_table: dict[str, Any]) -> list[dict[str, Any]]:
        """Return all routes with enriched target_type field."""
        enriched = []
        for route in route_table.get("routes", []):
            enriched.append(
                {
                    **route,
                    "target_type": self._resolve_target_type(route).value,
                    "target_id": self._resolve_target_id(route),
                }
            )
        return enriched

    @staticmethod
    def _resolve_target_type(route: dict[str, Any]) -> RouteTarget:
        if route.get("gateway_id", "").startswith("igw-"):
            return RouteTarget.IGW
        if route.get("nat_gateway_id", ""):
            return RouteTarget.NAT
        if route.get("transit_gateway_id", ""):
            return RouteTarget.TGW
        if route.get("vpc_peering_connection_id", ""):
            return RouteTarget.VPC_PEERING
        if route.get("network_interface_id", ""):
            return RouteTarget.NETWORK_INTERFACE
        if route.get("instance_id", ""):
            return RouteTarget.INSTANCE
        if route.get("gateway_id") == "local":
            return RouteTarget.LOCAL
        return RouteTarget.UNKNOWN

    @staticmethod
    def _resolve_target_id(route: dict[str, Any]) -> str:
        return (
            route.get("gateway_id")
            or route.get("nat_gateway_id")
            or route.get("transit_gateway_id")
            or route.get("vpc_peering_connection_id")
            or route.get("network_interface_id")
            or route.get("instance_id")
            or ""
        )
