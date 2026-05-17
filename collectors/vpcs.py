from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::vpc"


class VPCCollector:
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
        logger.info("[%s][%s] Collecting VPCs", self.account_name, self.region)
        try:
            vpcs = paginate(self.client, "describe_vpcs", "Vpcs")
            return [self._normalize(v) for v in vpcs]
        except Exception as exc:
            logger.error("[%s][%s] VPCs failed: %s", self.account_name, self.region, exc)
            return []

    def _normalize(self, vpc: dict[str, Any]) -> dict[str, Any]:
        vpc_id = vpc["VpcId"]
        relationships = []
        if dhcp_id := vpc.get("DhcpOptionsId"):
            relationships.append(
                build_relationship("aws::ec2::dhcp_options", dhcp_id, "uses_dhcp")
            )
        return {
            "resource_type": RESOURCE_TYPE,
            "resource_id": vpc_id,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "region": self.region,
            "cidr_block": vpc.get("CidrBlock", ""),
            "cidr_block_associations": [
                a.get("CidrBlock", "") for a in vpc.get("CidrBlockAssociationSet", [])
            ],
            "ipv6_cidr_blocks": [
                a.get("Ipv6CidrBlock", "")
                for a in vpc.get("Ipv6CidrBlockAssociationSet", [])
            ],
            "state": vpc.get("State", ""),
            "is_default": vpc.get("IsDefault", False),
            "dhcp_options_id": vpc.get("DhcpOptionsId", ""),
            "instance_tenancy": vpc.get("InstanceTenancy", ""),
            "tags": normalize_tags(vpc.get("Tags")),
            "relationships": relationships,
            "collected_at": utc_now(),
        }
