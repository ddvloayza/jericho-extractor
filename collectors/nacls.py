from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::network_acl"


class NACLCollector:
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
        logger.info("[%s][%s] Collecting NACLs", self.account_name, self.region)
        try:
            nacls = paginate(self.client, "describe_network_acls", "NetworkAcls")
            return [self._normalize(n) for n in nacls]
        except Exception as exc:
            logger.error("[%s][%s] NACLs failed: %s", self.account_name, self.region, exc)
            return []

    def _normalize(self, nacl: dict[str, Any]) -> dict[str, Any]:
        nacl_id = nacl["NetworkAclId"]
        vpc_id = nacl.get("VpcId", "")
        associations = nacl.get("Associations", [])
        associated_subnet_ids = [a["SubnetId"] for a in associations if "SubnetId" in a]

        relationships = []
        if vpc_id:
            relationships.append(build_relationship("aws::ec2::vpc", vpc_id, "belongs_to_vpc"))
        for subnet_id in associated_subnet_ids:
            relationships.append(
                build_relationship("aws::ec2::subnet", subnet_id, "associated_with_subnet")
            )

        entries = nacl.get("Entries", [])
        inbound = [self._normalize_entry(e) for e in entries if not e.get("Egress", False)]
        outbound = [self._normalize_entry(e) for e in entries if e.get("Egress", False)]

        return {
            "resource_type": RESOURCE_TYPE,
            "resource_id": nacl_id,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "region": self.region,
            "vpc_id": vpc_id,
            "is_default": nacl.get("IsDefault", False),
            "associated_subnet_ids": associated_subnet_ids,
            "inbound_rules": inbound,
            "outbound_rules": outbound,
            "tags": normalize_tags(nacl.get("Tags")),
            "relationships": relationships,
            "collected_at": utc_now(),
        }

    @staticmethod
    def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "rule_number": entry.get("RuleNumber"),
            "protocol": entry.get("Protocol", ""),
            "rule_action": entry.get("RuleAction", ""),
            "cidr_block": entry.get("CidrBlock", ""),
            "ipv6_cidr_block": entry.get("Ipv6CidrBlock", ""),
            "from_port": entry.get("PortRange", {}).get("From"),
            "to_port": entry.get("PortRange", {}).get("To"),
        }
