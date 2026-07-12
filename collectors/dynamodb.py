"""
DynamoDB collector.

Output file: dynamodb.json

Required IAM permissions (read-only):
  dynamodb:ListTables
  dynamodb:DescribeTable
  dynamodb:ListTagsOfResource
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::dynamodb::table"


class DynamoDBCollector:
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
        logger.info("[%s][%s] Collecting DynamoDB tables", self.account_name, self.region)
        try:
            table_names = paginate(self.client, "list_tables", "TableNames")
        except Exception as exc:
            logger.error("[%s][%s] DynamoDB tables failed: %s", self.account_name, self.region, exc)
            return []

        results = []
        for name in table_names:
            record = self._describe_table(name)
            if record:
                results.append(record)
        return results

    def _describe_table(self, name: str) -> dict[str, Any] | None:
        try:
            table = self.client.describe_table(TableName=name).get("Table", {})
        except Exception as exc:
            logger.debug("[%s][%s] describe_table failed for %s: %s",
                         self.account_name, self.region, name, exc)
            return None

        arn = table.get("TableArn", "")
        billing_mode = table.get("BillingModeSummary", {}).get("BillingMode", "PROVISIONED")
        throughput   = table.get("ProvisionedThroughput", {}) or {}
        gsis         = table.get("GlobalSecondaryIndexes", []) or []

        return {
            "resource_type":         RESOURCE_TYPE,
            "resource_id":           arn or name,
            "resource_name":         name,
            "account_id":            self.account_id,
            "account_name":          self.account_name,
            "region":                self.region,
            "status":                table.get("TableStatus", ""),
            "billing_mode":          billing_mode,
            "read_capacity_units":   throughput.get("ReadCapacityUnits", 0),
            "write_capacity_units":  throughput.get("WriteCapacityUnits", 0),
            "item_count":            table.get("ItemCount", 0),
            "table_size_bytes":      table.get("TableSizeBytes", 0),
            "global_secondary_indexes": len(gsis),
            "stream_enabled":        table.get("StreamSpecification", {}).get("StreamEnabled", False),
            "sse_enabled":           (table.get("SSEDescription", {}) or {}).get("Status", "") == "ENABLED",
            "creation_date":         str(table.get("CreationDateTime", "")),
            "tags":                  self._get_tags(arn),
            "collected_at":          utc_now(),
        }

    def _get_tags(self, arn: str) -> dict[str, str]:
        if not arn:
            return {}
        try:
            resp = self.client.list_tags_of_resource(ResourceArn=arn)
            return {t["Key"]: t["Value"] for t in resp.get("Tags", [])}
        except Exception:
            return {}
