"""
SNS (Simple Notification Service) collector.

Output file: sns.json

Required IAM permissions (read-only):
  sns:ListTopics
  sns:GetTopicAttributes
  sns:ListTagsForResource
  sns:ListSubscriptionsByTopic
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::sns::topic"


class SNSCollector:
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
        logger.info("[%s][%s] Collecting SNS topics", self.account_name, self.region)
        try:
            topics = paginate(self.client, "list_topics", "Topics")
        except Exception as exc:
            logger.error("[%s][%s] SNS topics failed: %s", self.account_name, self.region, exc)
            return []

        results = []
        for t in topics:
            record = self._describe_topic(t.get("TopicArn", ""))
            if record:
                results.append(record)
        return results

    def _describe_topic(self, arn: str) -> dict[str, Any] | None:
        if not arn:
            return None
        try:
            attrs = self.client.get_topic_attributes(TopicArn=arn).get("Attributes", {})
        except Exception as exc:
            logger.debug("[%s][%s] get_topic_attributes failed for %s: %s",
                         self.account_name, self.region, arn, exc)
            return None

        name = arn.rsplit(":", 1)[-1]
        sub_count = self._count_subscriptions(arn)

        return {
            "resource_type":            RESOURCE_TYPE,
            "resource_id":              arn,
            "resource_name":            name,
            "account_id":               self.account_id,
            "account_name":             self.account_name,
            "region":                   self.region,
            "display_name":             attrs.get("DisplayName", ""),
            "fifo_topic":               attrs.get("FifoTopic", "false") == "true",
            "subscriptions_confirmed":  int(attrs.get("SubscriptionsConfirmed", 0)),
            "subscriptions_pending":    int(attrs.get("SubscriptionsPending", 0)),
            "subscription_count":       sub_count,
            "kms_master_key_id":        attrs.get("KmsMasterKeyId", ""),
            "tags":                     self._get_tags(arn),
            "collected_at":             utc_now(),
        }

    def _count_subscriptions(self, arn: str) -> int:
        try:
            subs = paginate(self.client, "list_subscriptions_by_topic", "Subscriptions", TopicArn=arn)
            return len(subs)
        except Exception:
            return 0

    def _get_tags(self, arn: str) -> dict[str, str]:
        try:
            tags = self.client.list_tags_for_resource(ResourceArn=arn).get("Tags", [])
            return {t["Key"]: t["Value"] for t in tags}
        except Exception:
            return {}
