from __future__ import annotations

import json
import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::iam::role"


class IAMRolesCollector:
    """Collect IAM roles — trust policies, attached/inline policy names, trusted services.

    IAM is a global service; region is always 'global' for output consistency.
    Policy documents are NOT downloaded — only names and ARNs are captured.
    """

    def __init__(
        self,
        client: BaseClient,
        account_id: str,
        account_name: str,
    ) -> None:
        self.client = client
        self.account_id = account_id
        self.account_name = account_name

    def collect(self) -> list[dict[str, Any]]:
        logger.info("[%s][global] Collecting IAM roles", self.account_name)
        try:
            roles = paginate(self.client, "list_roles", "Roles")
            return [self._normalize(role) for role in roles]
        except Exception as exc:
            logger.error("[%s][global] IAM roles failed: %s", self.account_name, exc)
            return []

    def _normalize(self, role: dict[str, Any]) -> dict[str, Any]:
        role_arn  = role["Arn"]
        role_name = role["RoleName"]

        trust_doc     = role.get("AssumeRolePolicyDocument") or {}
        trusted_services = self._extract_trusted_services(trust_doc)
        trusted_accounts = self._extract_trusted_accounts(trust_doc)

        attached_policies = self._list_attached_policies(role_name)
        inline_policy_names = self._list_inline_policy_names(role_name)
        tags = self._fetch_tags(role_name)

        relationships: list[dict[str, str]] = []
        for policy in attached_policies:
            relationships.append(
                build_relationship("aws::iam::policy", policy["PolicyArn"], "has_attached_policy")
            )

        return {
            "resource_type":         RESOURCE_TYPE,
            "resource_id":           role_arn,
            "resource_name":         role_name,
            "account_id":            self.account_id,
            "account_name":          self.account_name,
            "region":                "global",
            "path":                  role.get("Path", ""),
            "description":           role.get("Description", ""),
            "max_session_duration":  role.get("MaxSessionDuration", 3600),
            "create_date":           str(role.get("CreateDate", "")),
            "trust_policy":          trust_doc,
            "trusted_services":      trusted_services,
            "trusted_accounts":      trusted_accounts,
            "attached_policies":     attached_policies,
            "inline_policy_names":   inline_policy_names,
            "tags":                  tags,
            "relationships":         relationships,
            "collected_at":          utc_now(),
        }

    def _extract_trusted_services(self, trust_doc: dict[str, Any]) -> list[str]:
        services: list[str] = []
        for stmt in trust_doc.get("Statement") or []:
            principal = stmt.get("Principal") or {}
            if isinstance(principal, str):
                continue
            svc = principal.get("Service") or []
            if isinstance(svc, str):
                svc = [svc]
            services.extend(svc)
        return sorted(set(services))

    def _extract_trusted_accounts(self, trust_doc: dict[str, Any]) -> list[str]:
        accounts: list[str] = []
        for stmt in trust_doc.get("Statement") or []:
            principal = stmt.get("Principal") or {}
            if isinstance(principal, str):
                # e.g. "Principal": "*"
                continue
            aws = principal.get("AWS") or []
            if isinstance(aws, str):
                aws = [aws]
            for arn in aws:
                # extract account ID from arn like arn:aws:iam::123456789012:root
                parts = arn.split(":")
                if len(parts) >= 5 and parts[4].isdigit():
                    accounts.append(parts[4])
        return sorted(set(accounts))

    def _list_attached_policies(self, role_name: str) -> list[dict[str, str]]:
        try:
            policies = paginate(
                self.client, "list_attached_role_policies", "AttachedPolicies",
                RoleName=role_name,
            )
            return [{"PolicyName": p["PolicyName"], "PolicyArn": p["PolicyArn"]} for p in policies]
        except Exception as exc:
            logger.debug("list_attached_role_policies failed for %s: %s", role_name, exc)
            return []

    def _list_inline_policy_names(self, role_name: str) -> list[str]:
        try:
            return paginate(self.client, "list_role_policies", "PolicyNames", RoleName=role_name)
        except Exception as exc:
            logger.debug("list_role_policies failed for %s: %s", role_name, exc)
            return []

    def _fetch_tags(self, role_name: str) -> dict[str, str]:
        try:
            tags = paginate(self.client, "list_role_tags", "Tags", RoleName=role_name)
            return {t["Key"]: t["Value"] for t in tags}
        except Exception:
            return {}
