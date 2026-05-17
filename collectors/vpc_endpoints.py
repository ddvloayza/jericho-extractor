from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::vpc_endpoint"


class VPCEndpointCollector:
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
        logger.info("[%s][%s] Collecting VPC Endpoints", self.account_name, self.region)
        try:
            endpoints = paginate(self.client, "describe_vpc_endpoints", "VpcEndpoints")
            return [self._normalize(e) for e in endpoints]
        except Exception as exc:
            logger.error(
                "[%s][%s] VPC Endpoints failed: %s", self.account_name, self.region, exc
            )
            return []

    def _normalize(self, ep: dict[str, Any]) -> dict[str, Any]:
        ep_id = ep["VpcEndpointId"]
        vpc_id = ep.get("VpcId", "")
        subnet_ids = ep.get("SubnetIds", [])
        route_table_ids = ep.get("RouteTableIds", [])

        relationships = []
        if vpc_id:
            relationships.append(build_relationship("aws::ec2::vpc", vpc_id, "belongs_to_vpc"))
        for subnet_id in subnet_ids:
            relationships.append(
                build_relationship("aws::ec2::subnet", subnet_id, "deployed_in_subnet")
            )

        return {
            "resource_type": RESOURCE_TYPE,
            "resource_id": ep_id,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "region": self.region,
            "vpc_id": vpc_id,
            "service_name": ep.get("ServiceName", ""),
            "endpoint_type": ep.get("VpcEndpointType", ""),
            "state": ep.get("State", ""),
            "associated_subnet_ids": subnet_ids,
            "associated_route_table_ids": route_table_ids,
            "dns_entries": [d.get("DnsName", "") for d in ep.get("DnsEntries", [])],
            "network_interface_ids": ep.get("NetworkInterfaceIds", []),
            "tags": normalize_tags(ep.get("Tags")),
            "relationships": relationships,
            "collected_at": utc_now(),
        }
