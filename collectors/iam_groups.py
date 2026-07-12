"""
IAM Groups collector.

IAM is a global service; region is always 'global' for output consistency.

Output file: iam_groups.json

Required IAM permissions (read-only):
  iam:ListGroups
  iam:ListAttachedGroupPolicies
  iam:ListGroupPolicies
  iam:GetGroup
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::iam::group"


class IAMGroupsCollector:
    def __init__(
        self,
        client: BaseClient,
        account_id: str,
        account_name: str,
    ) -> None:
        self.client       = client
        self.account_id   = account_id
        self.account_name = account_name

    def collect(self) -> list[dict[str, Any]]:
        logger.info("[%s][global] Collecting IAM groups", self.account_name)
        try:
            groups = paginate(self.client, "list_groups", "Groups")
            return [self._normalize(g) for g in groups]
        except Exception as exc:
            logger.error("[%s][global] IAM groups failed: %s", self.account_name, exc)
            return []

    def _normalize(self, group: dict[str, Any]) -> dict[str, Any]:
        group_name = group["GroupName"]
        group_arn  = group["Arn"]

        return {
            "resource_type":       RESOURCE_TYPE,
            "resource_id":         group_arn,
            "resource_name":       group_name,
            "account_id":          self.account_id,
            "account_name":        self.account_name,
            "region":              "global",
            "path":                group.get("Path", ""),
            "create_date":         str(group.get("CreateDate", "")),
            "attached_policies":   self._list_attached_policies(group_name),
            "inline_policy_names": self._list_inline_policy_names(group_name),
            "member_user_names":   self._list_members(group_name),
            "tags":                {},
            "collected_at":        utc_now(),
        }

    def _list_attached_policies(self, group_name: str) -> list[dict[str, str]]:
        try:
            policies = paginate(
                self.client, "list_attached_group_policies", "AttachedPolicies",
                GroupName=group_name,
            )
            return [{"PolicyName": p["PolicyName"], "PolicyArn": p["PolicyArn"]} for p in policies]
        except Exception:
            return []

    def _list_inline_policy_names(self, group_name: str) -> list[str]:
        try:
            return paginate(self.client, "list_group_policies", "PolicyNames", GroupName=group_name)
        except Exception:
            return []

    def _list_members(self, group_name: str) -> list[str]:
        try:
            resp = self.client.get_group(GroupName=group_name)
            return [u["UserName"] for u in resp.get("Users", [])]
        except Exception:
            return []
