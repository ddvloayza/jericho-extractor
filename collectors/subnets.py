from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::subnet"


class SubnetCollector:
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
        logger.info("[%s][%s] Collecting Subnets", self.account_name, self.region)
        try:
            subnets = paginate(self.client, "describe_subnets", "Subnets")
            return [self._normalize(s) for s in subnets]
        except Exception as exc:
            logger.error("[%s][%s] Subnets failed: %s", self.account_name, self.region, exc)
            return []

    def _normalize(self, subnet: dict[str, Any]) -> dict[str, Any]:
        subnet_id = subnet["SubnetId"]
        vpc_id = subnet.get("VpcId", "")
        relationships = []
        if vpc_id:
            relationships.append(build_relationship("aws::ec2::vpc", vpc_id, "belongs_to_vpc"))
        return {
            "resource_type": RESOURCE_TYPE,
            "resource_id": subnet_id,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "region": self.region,
            "vpc_id": vpc_id,
            "cidr_block": subnet.get("CidrBlock", ""),
            "ipv6_cidr_block": subnet.get("Ipv6CidrBlockAssociationSet", [{}])[0].get(
                "Ipv6CidrBlock", ""
            )
            if subnet.get("Ipv6CidrBlockAssociationSet")
            else "",
            "availability_zone": subnet.get("AvailabilityZone", ""),
            "availability_zone_id": subnet.get("AvailabilityZoneId", ""),
            "available_ip_count": subnet.get("AvailableIpAddressCount", 0),
            "state": subnet.get("State", ""),
            "is_default": subnet.get("DefaultForAz", False),
            "map_public_ip_on_launch": subnet.get("MapPublicIpOnLaunch", False),
            "subnet_type": "unknown",  # classified later by topology/subnet_classifier
            "tags": normalize_tags(subnet.get("Tags")),
            "relationships": relationships,
            "collected_at": utc_now(),
        }
