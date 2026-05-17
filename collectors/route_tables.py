from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::route_table"


class RouteTableCollector:
    def __init__(
        self,
        client: BaseClient,
        account_id: str,
        account_name: str,
        region: str,
    ) -> None:
        self.client = client
        self.account_id = account_id
        self.account_name = account_name
        self.region = region

    def collect(self) -> list[dict[str, Any]]:
        logger.info("[%s][%s] Collecting Route Tables", self.account_name, self.region)
        try:
            rts = paginate(self.client, "describe_route_tables", "RouteTables")
            return [self._normalize(rt) for rt in rts]
        except Exception as exc:
            logger.error(
                "[%s][%s] Route Tables failed: %s", self.account_name, self.region, exc
            )
            return []

    def _normalize(self, rt: dict[str, Any]) -> dict[str, Any]:
        rt_id = rt["RouteTableId"]
        vpc_id = rt.get("VpcId", "")
        associations = rt.get("Associations", [])
        is_main = any(a.get("Main", False) for a in associations)
        associated_subnet_ids = [
            a["SubnetId"] for a in associations if "SubnetId" in a
        ]

        relationships = []
        if vpc_id:
            relationships.append(build_relationship("aws::ec2::vpc", vpc_id, "belongs_to_vpc"))
        for subnet_id in associated_subnet_ids:
            relationships.append(
                build_relationship("aws::ec2::subnet", subnet_id, "associated_with_subnet")
            )

        routes = [self._normalize_route(r) for r in rt.get("Routes", [])]

        return {
            "resource_type": RESOURCE_TYPE,
            "resource_id": rt_id,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "region": self.region,
            "vpc_id": vpc_id,
            "is_main": is_main,
            "associated_subnet_ids": associated_subnet_ids,
            "routes": routes,
            "tags": normalize_tags(rt.get("Tags")),
            "relationships": relationships,
            "collected_at": utc_now(),
        }

    @staticmethod
    def _normalize_route(route: dict[str, Any]) -> dict[str, Any]:
        return {
            "destination_cidr": route.get("DestinationCidrBlock", ""),
            "destination_ipv6_cidr": route.get("DestinationIpv6CidrBlock", ""),
            "destination_prefix_list_id": route.get("DestinationPrefixListId", ""),
            "gateway_id": route.get("GatewayId", ""),
            "nat_gateway_id": route.get("NatGatewayId", ""),
            "transit_gateway_id": route.get("TransitGatewayId", ""),
            "vpc_peering_connection_id": route.get("VpcPeeringConnectionId", ""),
            "network_interface_id": route.get("NetworkInterfaceId", ""),
            "instance_id": route.get("InstanceId", ""),
            "state": route.get("State", ""),
            "origin": route.get("Origin", ""),
        }
