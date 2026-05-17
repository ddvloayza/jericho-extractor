from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::transit_gateway"


class TransitGatewayCollector:
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
        logger.info("[%s][%s] Collecting Transit Gateways", self.account_name, self.region)
        try:
            tgws = paginate(self.client, "describe_transit_gateways", "TransitGateways")
            # only collect TGWs owned by this account
            owned = [t for t in tgws if t.get("OwnerId") == self.account_id]
            return [self._normalize(t) for t in owned]
        except Exception as exc:
            logger.error(
                "[%s][%s] Transit Gateways failed: %s", self.account_name, self.region, exc
            )
            return []

    def _normalize(self, tgw: dict[str, Any]) -> dict[str, Any]:
        tgw_id = tgw["TransitGatewayId"]
        options = tgw.get("Options", {})
        return {
            "resource_type": RESOURCE_TYPE,
            "resource_id": tgw_id,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "region": self.region,
            "state": tgw.get("State", ""),
            "owner_id": tgw.get("OwnerId", ""),
            "description": tgw.get("Description", ""),
            "amazon_side_asn": options.get("AmazonSideAsn"),
            "auto_accept_shared_attachments": options.get(
                "AutoAcceptSharedAttachments", ""
            ),
            "default_route_table_association": options.get(
                "DefaultRouteTableAssociation", ""
            ),
            "default_route_table_propagation": options.get(
                "DefaultRouteTablePropagation", ""
            ),
            "vpn_ecmp_support": options.get("VpnEcmpSupport", ""),
            "dns_support": options.get("DnsSupport", ""),
            "tags": normalize_tags(tgw.get("Tags")),
            "relationships": [],
            "collected_at": utc_now(),
        }
