from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::nat_gateway"


class NatGatewayCollector:
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
        logger.info("[%s][%s] Collecting NAT Gateways", self.account_name, self.region)
        try:
            gateways = paginate(self.client, "describe_nat_gateways", "NatGateways")
            return [self._normalize(gw) for gw in gateways]
        except Exception as exc:
            logger.error(
                "[%s][%s] NAT Gateways failed: %s", self.account_name, self.region, exc
            )
            return []

    def _normalize(self, gw: dict[str, Any]) -> dict[str, Any]:
        gw_id = gw["NatGatewayId"]
        vpc_id = gw.get("VpcId", "")
        subnet_id = gw.get("SubnetId", "")

        addresses = gw.get("NatGatewayAddresses", [])
        public_ip = addresses[0].get("PublicIp", "") if addresses else ""
        private_ip = addresses[0].get("PrivateIp", "") if addresses else ""

        relationships = []
        if vpc_id:
            relationships.append(build_relationship("aws::ec2::vpc", vpc_id, "belongs_to_vpc"))
        if subnet_id:
            relationships.append(
                build_relationship("aws::ec2::subnet", subnet_id, "deployed_in_subnet")
            )

        return {
            "resource_type": RESOURCE_TYPE,
            "resource_id": gw_id,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "region": self.region,
            "vpc_id": vpc_id,
            "subnet_id": subnet_id,
            "state": gw.get("State", ""),
            "connectivity_type": gw.get("ConnectivityType", ""),
            "public_ip": public_ip,
            "private_ip": private_ip,
            "tags": normalize_tags(gw.get("Tags")),
            "relationships": relationships,
            "collected_at": utc_now(),
        }
