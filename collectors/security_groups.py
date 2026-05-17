from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::security_group"


class SecurityGroupCollector:
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
        logger.info("[%s][%s] Collecting Security Groups", self.account_name, self.region)
        try:
            sgs = paginate(self.client, "describe_security_groups", "SecurityGroups")
            return [self._normalize(sg) for sg in sgs]
        except Exception as exc:
            logger.error(
                "[%s][%s] Security Groups failed: %s", self.account_name, self.region, exc
            )
            return []

    def _normalize(self, sg: dict[str, Any]) -> dict[str, Any]:
        sg_id = sg["GroupId"]
        vpc_id = sg.get("VpcId", "")

        relationships = []
        if vpc_id:
            relationships.append(build_relationship("aws::ec2::vpc", vpc_id, "belongs_to_vpc"))

        return {
            "resource_type": RESOURCE_TYPE,
            "resource_id": sg_id,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "region": self.region,
            "vpc_id": vpc_id,
            "group_name": sg.get("GroupName", ""),
            "description": sg.get("Description", ""),
            "inbound_rules": [self._normalize_rule(r) for r in sg.get("IpPermissions", [])],
            "outbound_rules": [
                self._normalize_rule(r) for r in sg.get("IpPermissionsEgress", [])
            ],
            "tags": normalize_tags(sg.get("Tags")),
            "relationships": relationships,
            "collected_at": utc_now(),
        }

    @staticmethod
    def _normalize_rule(rule: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocol": rule.get("IpProtocol", ""),
            "from_port": rule.get("FromPort"),
            "to_port": rule.get("ToPort"),
            "ipv4_ranges": [r.get("CidrIp", "") for r in rule.get("IpRanges", [])],
            "ipv6_ranges": [
                r.get("CidrIpv6", "") for r in rule.get("Ipv6Ranges", [])
            ],
            "referenced_group_ids": [
                p.get("GroupId", "") for p in rule.get("UserIdGroupPairs", [])
            ],
            "prefix_list_ids": [
                p.get("PrefixListId", "") for p in rule.get("PrefixListIds", [])
            ],
        }
