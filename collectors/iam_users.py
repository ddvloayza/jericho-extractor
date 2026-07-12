"""
IAM Users collector.

IAM is a global service; region is always 'global' for output consistency.
Mirrors iam_roles.py's threaded pattern — per-user calls (policies, groups,
access keys, MFA) are parallelized since accounts can have many users.

Flags two common security signals:
  - mfa_enabled: False           -> user can log in without MFA
  - access_keys with age_days > 90 -> stale credential, should be rotated

Output file: iam_users.json

Required IAM permissions (read-only):
  iam:ListUsers
  iam:ListAttachedUserPolicies
  iam:ListUserPolicies
  iam:ListGroupsForUser
  iam:ListAccessKeys
  iam:ListMFADevices
  iam:ListUserTags
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::iam::user"

_MAX_WORKERS = 10
_PROGRESS_EVERY = 50


class IAMUsersCollector:
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
        logger.info("[%s][global] Collecting IAM users", self.account_name)
        try:
            users = paginate(self.client, "list_users", "Users")
        except Exception as exc:
            logger.error("[%s][global] IAM users failed: %s", self.account_name, exc)
            return []

        total = len(users)
        results: list[dict[str, Any]] = []
        done = 0
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {pool.submit(self._normalize, u): u for u in users}
            for future in as_completed(futures):
                results.append(future.result())
                done += 1
                if done % _PROGRESS_EVERY == 0 or done == total:
                    logger.info("[%s][global] IAM users processed: %d/%d", self.account_name, done, total)

        return results

    def _normalize(self, user: dict[str, Any]) -> dict[str, Any]:
        user_name = user["UserName"]
        user_arn  = user["Arn"]

        attached_policies = self._list_attached_policies(user_name)
        inline_policy_names = self._list_inline_policy_names(user_name)
        groups = self._list_groups(user_name)
        access_keys = self._list_access_keys(user_name)
        mfa_devices = self._list_mfa_devices(user_name)
        tags = self._fetch_tags(user_name)

        return {
            "resource_type":       RESOURCE_TYPE,
            "resource_id":         user_arn,
            "resource_name":       user_name,
            "account_id":          self.account_id,
            "account_name":        self.account_name,
            "region":              "global",
            "path":                user.get("Path", ""),
            "create_date":         str(user.get("CreateDate", "")),
            "password_last_used":  str(user.get("PasswordLastUsed", "")),
            "mfa_enabled":         len(mfa_devices) > 0,
            "groups":              groups,
            "attached_policies":   attached_policies,
            "inline_policy_names": inline_policy_names,
            "access_keys":         access_keys,
            "tags":                tags,
            "collected_at":        utc_now(),
        }

    def _list_attached_policies(self, user_name: str) -> list[dict[str, str]]:
        try:
            policies = paginate(
                self.client, "list_attached_user_policies", "AttachedPolicies",
                UserName=user_name,
            )
            return [{"PolicyName": p["PolicyName"], "PolicyArn": p["PolicyArn"]} for p in policies]
        except Exception:
            return []

    def _list_inline_policy_names(self, user_name: str) -> list[str]:
        try:
            return paginate(self.client, "list_user_policies", "PolicyNames", UserName=user_name)
        except Exception:
            return []

    def _list_groups(self, user_name: str) -> list[str]:
        try:
            groups = paginate(self.client, "list_groups_for_user", "Groups", UserName=user_name)
            return [g["GroupName"] for g in groups]
        except Exception:
            return []

    def _list_access_keys(self, user_name: str) -> list[dict[str, Any]]:
        try:
            keys = paginate(self.client, "list_access_keys", "AccessKeyMetadata", UserName=user_name)
        except Exception:
            return []

        result = []
        now = datetime.now(timezone.utc)
        for k in keys:
            create_date = k.get("CreateDate")
            age_days = None
            if create_date:
                dt = create_date if create_date.tzinfo else create_date.replace(tzinfo=timezone.utc)
                age_days = (now - dt).days
            result.append({
                "access_key_id": k.get("AccessKeyId", ""),
                "status":        k.get("Status", ""),
                "create_date":   str(create_date or ""),
                "age_days":      age_days,
                "stale":         (age_days or 0) > 90,
            })
        return result

    def _list_mfa_devices(self, user_name: str) -> list[dict[str, str]]:
        try:
            return paginate(self.client, "list_mfa_devices", "MFADevices", UserName=user_name)
        except Exception:
            return []

    def _fetch_tags(self, user_name: str) -> dict[str, str]:
        try:
            tags = paginate(self.client, "list_user_tags", "Tags", UserName=user_name)
            return {t["Key"]: t["Value"] for t in tags}
        except Exception:
            return {}
