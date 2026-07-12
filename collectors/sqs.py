"""
SQS (Simple Queue Service) collector.

Output file: sqs.json

Required IAM permissions (read-only):
  sqs:ListQueues
  sqs:GetQueueAttributes
  sqs:ListQueueTags
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::sqs::queue"


class SQSCollector:
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
        logger.info("[%s][%s] Collecting SQS queues", self.account_name, self.region)
        try:
            urls = paginate(self.client, "list_queues", "QueueUrls")
        except Exception as exc:
            logger.error("[%s][%s] SQS queues failed: %s", self.account_name, self.region, exc)
            return []

        results = []
        for url in urls:
            record = self._describe_queue(url)
            if record:
                results.append(record)
        return results

    def _describe_queue(self, url: str) -> dict[str, Any] | None:
        try:
            attrs = self.client.get_queue_attributes(
                QueueUrl=url, AttributeNames=["All"]
            ).get("Attributes", {})
        except Exception as exc:
            logger.debug("[%s][%s] get_queue_attributes failed for %s: %s",
                         self.account_name, self.region, url, exc)
            return None

        name = url.rsplit("/", 1)[-1]
        arn  = attrs.get("QueueArn", "")

        return {
            "resource_type":                RESOURCE_TYPE,
            "resource_id":                  arn or name,
            "resource_name":                name,
            "account_id":                   self.account_id,
            "account_name":                 self.account_name,
            "region":                       self.region,
            "queue_url":                    url,
            "fifo_queue":                   attrs.get("FifoQueue", "false") == "true",
            "visibility_timeout":           int(attrs.get("VisibilityTimeout", 30)),
            "message_retention_period":     int(attrs.get("MessageRetentionPeriod", 345600)),
            "approx_messages":              int(attrs.get("ApproximateNumberOfMessages", 0)),
            "approx_messages_in_flight":    int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0)),
            "approx_messages_delayed":      int(attrs.get("ApproximateNumberOfMessagesDelayed", 0)),
            "kms_master_key_id":            attrs.get("KmsMasterKeyId", ""),
            "redrive_policy":               attrs.get("RedrivePolicy", ""),
            "created_timestamp":            attrs.get("CreatedTimestamp", ""),
            "tags":                         self._get_tags(url),
            "collected_at":                 utc_now(),
        }

    def _get_tags(self, url: str) -> dict[str, str]:
        try:
            return self.client.list_queue_tags(QueueUrl=url).get("Tags", {})
        except Exception:
            return {}
