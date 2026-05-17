from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::elasticloadbalancingv2::loadbalancer"


class LoadBalancerCollector:
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
        logger.info("[%s][%s] Collecting Load Balancers", self.account_name, self.region)
        try:
            lbs = paginate(self.client, "describe_load_balancers", "LoadBalancers")
            return [self._normalize(lb) for lb in lbs]
        except Exception as exc:
            logger.error(
                "[%s][%s] Load Balancers failed: %s", self.account_name, self.region, exc
            )
            return []

    def _normalize(self, lb: dict[str, Any]) -> dict[str, Any]:
        lb_arn = lb["LoadBalancerArn"]
        lb_name = lb.get("LoadBalancerName", "")
        vpc_id = lb.get("VpcId", "")
        sg_ids = lb.get("SecurityGroups", [])

        azs = lb.get("AvailabilityZones", [])
        subnet_ids = [az.get("SubnetId", "") for az in azs if az.get("SubnetId")]

        relationships = []
        if vpc_id:
            relationships.append(build_relationship("aws::ec2::vpc", vpc_id, "deployed_in_vpc"))
        for subnet_id in subnet_ids:
            relationships.append(
                build_relationship("aws::ec2::subnet", subnet_id, "deployed_in_subnet")
            )
        for sg_id in sg_ids:
            relationships.append(
                build_relationship("aws::ec2::security_group", sg_id, "protected_by_sg")
            )

        # Fetch tags separately (ELBv2 tags API differs from EC2)
        tags = self._fetch_tags(lb_arn)

        return {
            "resource_type": RESOURCE_TYPE,
            "resource_id": lb_arn,
            "resource_name": lb_name,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "region": self.region,
            "dns_name": lb.get("DNSName", ""),
            "scheme": lb.get("Scheme", ""),
            "lb_type": lb.get("Type", ""),
            "state": lb.get("State", {}).get("Code", ""),
            "vpc_id": vpc_id,
            "availability_zones": azs,
            "security_group_ids": sg_ids,
            "canonical_hosted_zone_id": lb.get("CanonicalHostedZoneId", ""),
            "created_time": str(lb.get("CreatedTime", "")),
            "tags": tags,
            "relationships": relationships,
            "collected_at": utc_now(),
        }

    def _fetch_tags(self, arn: str) -> dict[str, str]:
        try:
            response = self.client.describe_tags(ResourceArns=[arn])
            for td in response.get("TagDescriptions", []):
                if td.get("ResourceArn") == arn:
                    return {t["Key"]: t["Value"] for t in td.get("Tags", [])}
        except Exception:
            pass
        return {}
