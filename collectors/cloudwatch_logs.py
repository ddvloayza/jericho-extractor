"""
CloudWatch Logs collector.

Log groups are a common hidden cost driver — default retention is "Never
expire", so log volume accumulates indefinitely unless someone sets a
retention policy. This collector flags exactly that.

Output file: cloudwatch_logs.json

Required IAM permissions (read-only):
  logs:DescribeLogGroups
  logs:ListTagsForResource

Pricing reference (approx, us-east-1 standard tier):
  ~$0.03/GB-month storage (ingestion cost is NOT knowable from log group
  metadata alone — this is a storage-only proxy, real cost is usually
  dominated by ingestion, not storage)
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::logs::loggroup"

_STORAGE_PRICE_PER_GB = 0.03


class CloudWatchLogsCollector:
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
        logger.info("[%s][%s] Collecting CloudWatch Log Groups", self.account_name, self.region)
        try:
            groups = paginate(self.client, "describe_log_groups", "logGroups")
            return [self._normalize(g) for g in groups]
        except Exception as exc:
            logger.error("[%s][%s] CloudWatch Log Groups failed: %s", self.account_name, self.region, exc)
            return []

    def _normalize(self, group: dict[str, Any]) -> dict[str, Any]:
        name = group.get("logGroupName", "")
        arn  = group.get("arn", "")
        stored_bytes    = group.get("storedBytes", 0) or 0
        retention_days  = group.get("retentionInDays")
        size_gb         = round(stored_bytes / (1024 ** 3), 4)
        est_cost_month  = round(size_gb * _STORAGE_PRICE_PER_GB, 4)

        return {
            "resource_type":       RESOURCE_TYPE,
            "resource_id":         arn or name,
            "resource_name":       name,
            "account_id":          self.account_id,
            "account_name":        self.account_name,
            "region":              self.region,
            "creation_time":       group.get("creationTime"),
            "retention_days":      retention_days,
            "no_expiration":       retention_days is None,
            "stored_bytes":        stored_bytes,
            "stored_gb":           size_gb,
            "metric_filter_count": group.get("metricFilterCount", 0),
            "est_cost_per_month":  est_cost_month,
            "tags":                self._get_tags(arn),
            "collected_at":        utc_now(),
        }

    def _get_tags(self, arn: str) -> dict[str, str]:
        if not arn:
            return {}
        try:
            resp = self.client.list_tags_for_resource(resourceArn=arn)
            return resp.get("tags", {})
        except Exception as exc:
            logger.debug("[%s][%s] list_tags_for_resource failed for %s: %s",
                         self.account_name, self.region, arn, exc)
            return {}
