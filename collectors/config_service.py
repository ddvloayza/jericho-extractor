"""
AWS Config collector — the configuration recorder, delivery channel, and
config rules that enforce tagging/compliance governance.

Named config_service.py (not config.py) to avoid clashing with the
project's own config.py (AccountConfig/AppConfig).

Output file: aws_config.json  (mixed resource_type: recorder + rule)

Required IAM permissions (read-only):
  config:DescribeConfigurationRecorders
  config:DescribeConfigurationRecorderStatus
  config:DescribeConfigRules
  config:DescribeDeliveryChannels
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now

logger = logging.getLogger(__name__)

RECORDER_RESOURCE_TYPE = "aws::config::configurationrecorder"
RULE_RESOURCE_TYPE     = "aws::config::configrule"


class ConfigServiceCollector:
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
        logger.info("[%s][%s] Collecting AWS Config (recorder + rules)", self.account_name, self.region)
        results: list[dict[str, Any]] = []
        results.extend(self._collect_recorders())
        results.extend(self._collect_rules())
        return results

    def _collect_recorders(self) -> list[dict[str, Any]]:
        try:
            recorders = self.client.describe_configuration_recorders().get("ConfigurationRecorders", [])
            statuses  = {
                s["name"]: s
                for s in self.client.describe_configuration_recorder_status()
                    .get("ConfigurationRecordersStatus", [])
            }
            channels  = self.client.describe_delivery_channels().get("DeliveryChannels", [])
        except Exception as exc:
            logger.error("[%s][%s] Config recorders failed: %s", self.account_name, self.region, exc)
            return []

        channel = channels[0] if channels else {}
        results = []
        for rec in recorders:
            name   = rec.get("name", "")
            status = statuses.get(name, {})
            results.append({
                "resource_type":     RECORDER_RESOURCE_TYPE,
                "resource_id":       name,
                "resource_name":     name,
                "account_id":        self.account_id,
                "account_name":      self.account_name,
                "region":            self.region,
                "recording":         status.get("recording", False),
                "last_status":       status.get("lastStatus", ""),
                "all_supported":     rec.get("recordingGroup", {}).get("allSupported", False),
                "include_global_resource_types": rec.get("recordingGroup", {}).get("includeGlobalResourceTypes", False),
                "delivery_channel_name": channel.get("name", ""),
                "delivery_s3_bucket":    channel.get("s3BucketName", ""),
                "tags":              {},
                "collected_at":      utc_now(),
            })
        return results

    def _collect_rules(self) -> list[dict[str, Any]]:
        try:
            rules = paginate(self.client, "describe_config_rules", "ConfigRules")
        except Exception as exc:
            logger.error("[%s][%s] Config rules failed: %s", self.account_name, self.region, exc)
            return []

        return [self._normalize_rule(r) for r in rules]

    def _normalize_rule(self, rule: dict[str, Any]) -> dict[str, Any]:
        source = rule.get("Source", {}) or {}
        return {
            "resource_type":  RULE_RESOURCE_TYPE,
            "resource_id":    rule.get("ConfigRuleArn", rule.get("ConfigRuleName", "")),
            "resource_name":  rule.get("ConfigRuleName", ""),
            "account_id":     self.account_id,
            "account_name":   self.account_name,
            "region":         self.region,
            "description":    rule.get("Description", ""),
            "source_owner":   source.get("Owner", ""),
            "source_identifier": source.get("SourceIdentifier", ""),
            "state":          rule.get("ConfigRuleState", ""),
            "scope":          rule.get("Scope", {}),
            "tags":           {},
            "collected_at":   utc_now(),
        }
