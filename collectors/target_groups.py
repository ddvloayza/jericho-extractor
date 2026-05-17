from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::elasticloadbalancingv2::targetgroup"


class TargetGroupCollector:
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
        logger.info("[%s][%s] Collecting Target Groups", self.account_name, self.region)
        try:
            tgs = paginate(self.client, "describe_target_groups", "TargetGroups")
            return [self._normalize(tg) for tg in tgs]
        except Exception as exc:
            logger.error(
                "[%s][%s] Target Groups failed: %s", self.account_name, self.region, exc
            )
            return []

    def _normalize(self, tg: dict[str, Any]) -> dict[str, Any]:
        tg_arn = tg["TargetGroupArn"]
        vpc_id = tg.get("VpcId", "")
        lb_arns = tg.get("LoadBalancerArns", [])

        relationships = []
        if vpc_id:
            relationships.append(build_relationship("aws::ec2::vpc", vpc_id, "belongs_to_vpc"))
        for lb_arn in lb_arns:
            relationships.append(
                build_relationship(
                    "aws::elasticloadbalancingv2::loadbalancer",
                    lb_arn,
                    "registered_on_lb",
                )
            )

        targets = self._fetch_targets(tg_arn)

        hc = tg.get("HealthCheckEnabled", False)
        return {
            "resource_type": RESOURCE_TYPE,
            "resource_id": tg_arn,
            "resource_name": tg.get("TargetGroupName", ""),
            "account_id": self.account_id,
            "account_name": self.account_name,
            "region": self.region,
            "protocol": tg.get("Protocol", ""),
            "port": tg.get("Port", 0),
            "vpc_id": vpc_id,
            "target_type": tg.get("TargetType", ""),
            "health_check_enabled": hc,
            "health_check_protocol": tg.get("HealthCheckProtocol", ""),
            "health_check_path": tg.get("HealthCheckPath", ""),
            "health_check_interval": tg.get("HealthCheckIntervalSeconds"),
            "healthy_threshold": tg.get("HealthyThresholdCount"),
            "unhealthy_threshold": tg.get("UnhealthyThresholdCount"),
            "load_balancer_arns": lb_arns,
            "targets": targets,
            "tags": {},
            "relationships": relationships,
            "collected_at": utc_now(),
        }

    def _fetch_targets(self, tg_arn: str) -> list[dict[str, Any]]:
        try:
            response = self.client.describe_target_health(TargetGroupArn=tg_arn)
            return [
                {
                    "id": th["Target"].get("Id", ""),
                    "port": th["Target"].get("Port"),
                    "health_state": th.get("TargetHealth", {}).get("State", ""),
                    "health_reason": th.get("TargetHealth", {}).get("Reason", ""),
                }
                for th in response.get("TargetHealthDescriptions", [])
            ]
        except Exception:
            return []
