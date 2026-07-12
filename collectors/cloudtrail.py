"""
CloudTrail collector.

Output file: cloudtrail.json

Required IAM permissions (read-only):
  cloudtrail:DescribeTrails
  cloudtrail:GetTrailStatus
  cloudtrail:ListTags
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import utc_now

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::cloudtrail::trail"


class CloudTrailCollector:
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
        logger.info("[%s][%s] Collecting CloudTrail trails", self.account_name, self.region)
        try:
            trails = self.client.describe_trails(includeShadowTrails=False).get("trailList", [])
            return [self._normalize(t) for t in trails]
        except Exception as exc:
            logger.error("[%s][%s] CloudTrail failed: %s", self.account_name, self.region, exc)
            return []

    def _normalize(self, trail: dict[str, Any]) -> dict[str, Any]:
        arn  = trail.get("TrailARN", "")
        name = trail.get("Name", "")

        return {
            "resource_type":              RESOURCE_TYPE,
            "resource_id":                arn or name,
            "resource_name":              name,
            "account_id":                 self.account_id,
            "account_name":               self.account_name,
            "region":                     self.region,
            "s3_bucket_name":             trail.get("S3BucketName", ""),
            "is_multi_region_trail":      trail.get("IsMultiRegionTrail", False),
            "is_organization_trail":      trail.get("IsOrganizationTrail", False),
            "log_file_validation_enabled": trail.get("LogFileValidationEnabled", False),
            "kms_key_id":                 trail.get("KmsKeyId", ""),
            "cloud_watch_logs_log_group_arn": trail.get("CloudWatchLogsLogGroupArn", ""),
            "is_logging":                 self._get_logging_status(arn),
            "home_region":                trail.get("HomeRegion", ""),
            "tags":                       self._get_tags(arn),
            "collected_at":               utc_now(),
        }

    def _get_logging_status(self, arn: str) -> bool:
        if not arn:
            return False
        try:
            return self.client.get_trail_status(Name=arn).get("IsLogging", False)
        except Exception:
            return False

    def _get_tags(self, arn: str) -> dict[str, str]:
        if not arn:
            return {}
        try:
            resp = self.client.list_tags(ResourceIdList=[arn])
            for entry in resp.get("ResourceTagList", []):
                if entry.get("ResourceId") == arn:
                    return {t["Key"]: t.get("Value", "") for t in entry.get("TagsList", [])}
            return {}
        except Exception:
            return {}
