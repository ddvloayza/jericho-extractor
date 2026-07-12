"""
EventBridge (CloudWatch Events) collector.

Output file: eventbridge.json

Required IAM permissions (read-only):
  events:ListEventBuses
  events:ListRules
  events:ListTargetsByRule
  events:ListTagsForResource
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::events::rule"


class EventBridgeCollector:
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
        logger.info("[%s][%s] Collecting EventBridge rules", self.account_name, self.region)
        try:
            buses = paginate(self.client, "list_event_buses", "EventBuses")
        except Exception as exc:
            logger.error("[%s][%s] EventBridge buses failed: %s", self.account_name, self.region, exc)
            return []

        results: list[dict[str, Any]] = []
        for bus in buses:
            bus_name = bus.get("Name", "default")
            try:
                rules = paginate(self.client, "list_rules", "Rules", EventBusName=bus_name)
            except Exception as exc:
                logger.debug("[%s][%s] list_rules failed for bus %s: %s",
                             self.account_name, self.region, bus_name, exc)
                continue
            for rule in rules:
                results.append(self._normalize(rule, bus_name))
        return results

    def _normalize(self, rule: dict[str, Any], bus_name: str) -> dict[str, Any]:
        name = rule.get("Name", "")
        arn  = rule.get("Arn", "")

        return {
            "resource_type":     RESOURCE_TYPE,
            "resource_id":       arn or name,
            "resource_name":     name,
            "account_id":        self.account_id,
            "account_name":      self.account_name,
            "region":            self.region,
            "event_bus_name":    bus_name,
            "state":             rule.get("State", ""),   # ENABLED / DISABLED
            "description":       rule.get("Description", ""),
            "schedule_expression": rule.get("ScheduleExpression", ""),
            "event_pattern":     rule.get("EventPattern", ""),
            "target_count":      self._count_targets(name, bus_name),
            "tags":              self._get_tags(arn),
            "collected_at":      utc_now(),
        }

    def _count_targets(self, rule_name: str, bus_name: str) -> int:
        try:
            targets = paginate(
                self.client, "list_targets_by_rule", "Targets",
                Rule=rule_name, EventBusName=bus_name,
            )
            return len(targets)
        except Exception:
            return 0

    def _get_tags(self, arn: str) -> dict[str, str]:
        if not arn:
            return {}
        try:
            tags = self.client.list_tags_for_resource(ResourceARN=arn).get("Tags", [])
            return {t["Key"]: t["Value"] for t in tags}
        except Exception:
            return {}
