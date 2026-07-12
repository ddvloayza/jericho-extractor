"""
AWS WAFv2 collector — regional Web ACLs only (CLOUDFRONT-scope ACLs are only
queryable from us-east-1 and are out of scope here to keep one collector per
region consistent with the rest of the tool).

Output file: waf.json

Required IAM permissions (read-only):
  wafv2:ListWebACLs
  wafv2:GetWebACL
  wafv2:ListTagsForResource

Note: list_web_acls returns up to 100 ACLs per call; this collector does not
paginate beyond what the API returns in one call (WAFv2 rarely has more than
a handful of Web ACLs per account/region).
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import utc_now

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::wafv2::webacl"


class WAFCollector:
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
        logger.info("[%s][%s] Collecting WAFv2 Web ACLs", self.account_name, self.region)
        try:
            acls = self.client.list_web_acls(Scope="REGIONAL").get("WebACLs", [])
        except Exception as exc:
            logger.error("[%s][%s] WAFv2 Web ACLs failed: %s", self.account_name, self.region, exc)
            return []

        results = []
        for acl in acls:
            record = self._describe(acl)
            if record:
                results.append(record)
        return results

    def _describe(self, acl_summary: dict[str, Any]) -> dict[str, Any] | None:
        name = acl_summary.get("Name", "")
        acl_id = acl_summary.get("Id", "")
        arn = acl_summary.get("ARN", "")

        try:
            detail = self.client.get_web_acl(Name=name, Scope="REGIONAL", Id=acl_id).get("WebACL", {})
        except Exception as exc:
            logger.debug("[%s][%s] get_web_acl failed for %s: %s",
                         self.account_name, self.region, name, exc)
            detail = {}

        rules = detail.get("Rules", []) or []

        return {
            "resource_type":   RESOURCE_TYPE,
            "resource_id":     arn or acl_id,
            "resource_name":   name,
            "account_id":      self.account_id,
            "account_name":    self.account_name,
            "region":          self.region,
            "description":     acl_summary.get("Description", ""),
            "capacity":        detail.get("Capacity", 0),
            "rule_count":      len(rules),
            "default_action":  list((detail.get("DefaultAction") or {}).keys()),
            "tags":            self._get_tags(arn),
            "collected_at":    utc_now(),
        }

    def _get_tags(self, arn: str) -> dict[str, str]:
        if not arn:
            return {}
        try:
            resp = self.client.list_tags_for_resource(ResourceARN=arn)
            tags = resp.get("TagInfoForResource", {}).get("TagList", [])
            return {t["Key"]: t.get("Value", "") for t in tags}
        except Exception:
            return {}
