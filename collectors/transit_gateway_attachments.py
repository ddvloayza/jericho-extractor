from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::transit_gateway_attachment"


class TransitGatewayAttachmentCollector:
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
        logger.info(
            "[%s][%s] Collecting Transit Gateway Attachments",
            self.account_name,
            self.region,
        )
        try:
            attachments = paginate(
                self.client,
                "describe_transit_gateway_attachments",
                "TransitGatewayAttachments",
            )
            return [self._normalize(a) for a in attachments]
        except Exception as exc:
            logger.error(
                "[%s][%s] TGW Attachments failed: %s", self.account_name, self.region, exc
            )
            return []

    def _normalize(self, att: dict[str, Any]) -> dict[str, Any]:
        att_id = att["TransitGatewayAttachmentId"]
        tgw_id = att.get("TransitGatewayId", "")
        resource_id = att.get("ResourceId", "")
        resource_type = att.get("ResourceType", "")

        relationships = []
        if tgw_id:
            relationships.append(
                build_relationship(
                    "aws::ec2::transit_gateway", tgw_id, "attached_to_tgw"
                )
            )
        if resource_id and resource_type == "vpc":
            relationships.append(
                build_relationship("aws::ec2::vpc", resource_id, "attachment_resource")
            )

        return {
            "resource_type": RESOURCE_TYPE,
            "resource_id": att_id,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "region": self.region,
            "transit_gateway_id": tgw_id,
            "transit_gateway_owner_id": att.get("TransitGatewayOwnerId", ""),
            "attachment_type": resource_type,
            "state": att.get("State", ""),
            "resource_id_ref": resource_id,
            "resource_owner_id": att.get("ResourceOwnerId", ""),
            "tags": normalize_tags(att.get("Tags")),
            "relationships": relationships,
            "collected_at": utc_now(),
        }
