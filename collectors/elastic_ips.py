"""
Elastic IP collector.

Unassociated Elastic IPs are billed hourly (~$3.60/month each) even though
they aren't attached to anything — an easy-to-forget cost leak. This
collector flags exactly which EIPs are orphaned.

Output file: elastic_ips.json

Required IAM permissions (read-only):
  ec2:DescribeAddresses

Pricing reference: $0.005/hour for an unassociated Elastic IP (~$3.60/month)
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::eip"

_UNASSOCIATED_PRICE_PER_MONTH = 3.60


class ElasticIPCollector:
    def __init__(
        self,
        client: BaseClient,
        account_id: str,
        account_name: str,
        region: str,
    ) -> None:
        self.client       = client
        self.account_id   = account_id
        self.account_name = account_name
        self.region       = region

    def collect(self) -> list[dict[str, Any]]:
        logger.info("[%s][%s] Collecting Elastic IPs", self.account_name, self.region)
        try:
            addresses = paginate(self.client, "describe_addresses", "Addresses")
            return [self._normalize(a) for a in addresses]
        except Exception as exc:
            logger.error("[%s][%s] Elastic IPs failed: %s", self.account_name, self.region, exc)
            return []

    def _normalize(self, addr: dict[str, Any]) -> dict[str, Any]:
        tags        = normalize_tags(addr.get("Tags"))
        instance_id = addr.get("InstanceId", "")
        assoc_id    = addr.get("AssociationId", "")
        is_associated = bool(instance_id or assoc_id)

        relationships: list[dict] = []
        if instance_id:
            relationships.append(
                build_relationship("aws::ec2::instance", instance_id, "associated_with_instance")
            )

        return {
            "resource_type":      RESOURCE_TYPE,
            "resource_id":        addr.get("AllocationId", addr.get("PublicIp", "")),
            "resource_name":      tags.get("Name", ""),
            "account_id":         self.account_id,
            "account_name":       self.account_name,
            "region":             self.region,
            "public_ip":          addr.get("PublicIp", ""),
            "domain":             addr.get("Domain", ""),
            "instance_id":        instance_id,
            "network_interface_id": addr.get("NetworkInterfaceId", ""),
            "is_associated":      is_associated,
            "est_cost_per_month": 0.0 if is_associated else _UNASSOCIATED_PRICE_PER_MONTH,
            "tags":               tags,
            "relationships":      relationships,
            "collected_at":       utc_now(),
        }
