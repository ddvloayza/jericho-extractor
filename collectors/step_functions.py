"""
AWS Step Functions collector.

Output file: step_functions.json

Required IAM permissions (read-only):
  states:ListStateMachines
  states:DescribeStateMachine
  states:ListTagsForResource
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::states::statemachine"


class StepFunctionsCollector:
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
        logger.info("[%s][%s] Collecting Step Functions state machines", self.account_name, self.region)
        try:
            machines = paginate(self.client, "list_state_machines", "stateMachines")
        except Exception as exc:
            logger.error("[%s][%s] Step Functions failed: %s", self.account_name, self.region, exc)
            return []

        results = []
        for m in machines:
            record = self._describe(m.get("stateMachineArn", ""))
            if record:
                results.append(record)
        return results

    def _describe(self, arn: str) -> dict[str, Any] | None:
        if not arn:
            return None
        try:
            detail = self.client.describe_state_machine(stateMachineArn=arn)
        except Exception as exc:
            logger.debug("[%s][%s] describe_state_machine failed for %s: %s",
                         self.account_name, self.region, arn, exc)
            return None

        return {
            "resource_type":  RESOURCE_TYPE,
            "resource_id":    arn,
            "resource_name":  detail.get("name", ""),
            "account_id":     self.account_id,
            "account_name":   self.account_name,
            "region":         self.region,
            "status":         detail.get("status", ""),
            "type":           detail.get("type", ""),   # STANDARD or EXPRESS
            "role_arn":       detail.get("roleArn", ""),
            "creation_date":  str(detail.get("creationDate", "")),
            "logging_level":  (detail.get("loggingConfiguration", {}) or {}).get("level", "OFF"),
            "tracing_enabled": (detail.get("tracingConfiguration", {}) or {}).get("enabled", False),
            "tags":           self._get_tags(arn),
            "collected_at":   utc_now(),
        }

    def _get_tags(self, arn: str) -> dict[str, str]:
        try:
            tags = self.client.list_tags_for_resource(resourceArn=arn).get("tags", [])
            return {t["key"]: t["value"] for t in tags}
        except Exception:
            return {}
