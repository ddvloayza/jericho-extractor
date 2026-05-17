from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::internet_gateway"


class InternetGatewayCollector:
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
        logger.info("[%s][%s] Collecting Internet Gateways", self.account_name, self.region)
        try:
            igws = paginate(self.client, "describe_internet_gateways", "InternetGateways")
            return [self._normalize(igw) for igw in igws]
        except Exception as exc:
            logger.error(
                "[%s][%s] Internet Gateways failed: %s", self.account_name, self.region, exc
            )
            return []

    def _normalize(self, igw: dict[str, Any]) -> dict[str, Any]:
        igw_id = igw["InternetGatewayId"]
        attachments = igw.get("Attachments", [])
        attached_vpc_ids = [a["VpcId"] for a in attachments if "VpcId" in a]
        state = attachments[0].get("State", "") if attachments else "detached"

        relationships = [
            build_relationship("aws::ec2::vpc", vpc_id, "attached_to_vpc")
            for vpc_id in attached_vpc_ids
        ]

        return {
            "resource_type": RESOURCE_TYPE,
            "resource_id": igw_id,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "region": self.region,
            "state": state,
            "attached_vpc_ids": attached_vpc_ids,
            "tags": normalize_tags(igw.get("Tags")),
            "relationships": relationships,
            "collected_at": utc_now(),
        }
