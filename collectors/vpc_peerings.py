from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::vpc_peering_connection"


class VPCPeeringCollector:
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
        logger.info("[%s][%s] Collecting VPC Peerings", self.account_name, self.region)
        try:
            peerings = paginate(
                self.client, "describe_vpc_peering_connections", "VpcPeeringConnections"
            )
            return [self._normalize(p) for p in peerings]
        except Exception as exc:
            logger.error(
                "[%s][%s] VPC Peerings failed: %s", self.account_name, self.region, exc
            )
            return []

    def _normalize(self, peering: dict[str, Any]) -> dict[str, Any]:
        pcx_id = peering["VpcPeeringConnectionId"]
        requester = peering.get("RequesterVpcInfo", {})
        accepter = peering.get("AccepterVpcInfo", {})

        relationships = []
        if req_vpc := requester.get("VpcId"):
            relationships.append(
                build_relationship("aws::ec2::vpc", req_vpc, "requester_vpc")
            )
        if acc_vpc := accepter.get("VpcId"):
            relationships.append(
                build_relationship("aws::ec2::vpc", acc_vpc, "accepter_vpc")
            )

        return {
            "resource_type": RESOURCE_TYPE,
            "resource_id": pcx_id,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "region": self.region,
            "status": peering.get("Status", {}).get("Code", ""),
            "status_message": peering.get("Status", {}).get("Message", ""),
            "requester_vpc_id": requester.get("VpcId", ""),
            "requester_account_id": requester.get("OwnerId", ""),
            "requester_region": requester.get("Region", ""),
            "requester_cidr": requester.get("CidrBlock", ""),
            "accepter_vpc_id": accepter.get("VpcId", ""),
            "accepter_account_id": accepter.get("OwnerId", ""),
            "accepter_region": accepter.get("Region", ""),
            "accepter_cidr": accepter.get("CidrBlock", ""),
            "tags": normalize_tags(peering.get("Tags")),
            "relationships": relationships,
            "collected_at": utc_now(),
        }
