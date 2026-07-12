"""
AWS Backup collector.

Read-only inventory of the AWS Backup service itself — the vaults, plans,
schedules, retention rules and resource selections that CREATE the
snapshots/AMIs already captured by ebs.py / snapshots.py / amis.py.

Those other collectors show the artifacts (a snapshot, an AMI). This
collector shows the POLICY that generated them — schedule, retention,
target resource — which is what you need to actually change a backup
strategy (e.g. "daily plan with 35-day retention on i-0016a8bc9ee8b94c7
is what creates the 13TB AMIs in Portal-Prod").

Output file: aws_backup.json  (mixed resource_type: vault + plan)

Required IAM permissions (all read-only):
  backup:ListBackupVaults
  backup:ListBackupPlans
  backup:GetBackupPlan
  backup:ListBackupSelections
  backup:GetBackupSelection
  backup:ListRecoveryPointsByBackupVault

Pricing reference (approx, varies by resource type and warm/cold tier):
  ~$0.05/GB-month warm storage — same proxy used in snapshots.py
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now

logger = logging.getLogger(__name__)

VAULT_RESOURCE_TYPE = "aws::backup::vault"
PLAN_RESOURCE_TYPE  = "aws::backup::plan"

# Approximate warm-storage pricing per GB/month (proxy — actual cost depends
# on resource type and cold/warm tier of each recovery point)
_BACKUP_PRICE_PER_GB = 0.05


class AWSBackupCollector:
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

    # ── public ────────────────────────────────────────────────────────────────

    def collect(self) -> list[dict[str, Any]]:
        logger.info(
            "[%s][%s] Collecting AWS Backup (vaults + plans)",
            self.account_name, self.region,
        )
        results: list[dict[str, Any]] = []
        results.extend(self._collect_vaults())
        results.extend(self._collect_plans())
        return results

    # ── vaults ────────────────────────────────────────────────────────────────

    def _collect_vaults(self) -> list[dict[str, Any]]:
        try:
            vaults = paginate(self.client, "list_backup_vaults", "BackupVaultList")
        except Exception as exc:
            logger.error(
                "[%s][%s] Backup vaults failed: %s", self.account_name, self.region, exc
            )
            return []

        return [self._normalize_vault(v) for v in vaults]

    def _normalize_vault(self, vault: dict[str, Any]) -> dict[str, Any]:
        vault_name = vault.get("BackupVaultName", "")
        vault_arn  = vault.get("BackupVaultArn", "")
        num_points = vault.get("NumberOfRecoveryPoints", 0)

        total_size_bytes = self._sum_recovery_point_size(vault_name)
        total_size_gb    = round(total_size_bytes / (1024 ** 3), 2)
        est_cost_month   = round(total_size_gb * _BACKUP_PRICE_PER_GB, 4)

        return {
            "resource_type":            VAULT_RESOURCE_TYPE,
            "resource_id":              vault_arn or vault_name,
            "resource_name":            vault_name,
            "account_id":               self.account_id,
            "account_name":             self.account_name,
            "region":                   self.region,
            "creation_date":            str(vault.get("CreationDate", "")),
            "encryption_key_arn":       vault.get("EncryptionKeyArn", ""),
            "number_of_recovery_points": num_points,
            "locked":                   vault.get("Locked", False),
            "min_retention_days":       vault.get("MinRetentionDays"),
            "max_retention_days":       vault.get("MaxRetentionDays"),
            "total_backup_size_bytes":  total_size_bytes,
            "total_backup_size_gb":     total_size_gb,
            "est_cost_per_month":       est_cost_month,
            "tags":                     {},
            "collected_at":             utc_now(),
        }

    def _sum_recovery_point_size(self, vault_name: str) -> int:
        if not vault_name:
            return 0
        try:
            points = paginate(
                self.client,
                "list_recovery_points_by_backup_vault",
                "RecoveryPoints",
                BackupVaultName=vault_name,
            )
            return sum(p.get("BackupSizeInBytes", 0) or 0 for p in points)
        except Exception as exc:
            logger.debug(
                "[%s][%s] Could not sum recovery points for vault %s: %s",
                self.account_name, self.region, vault_name, exc,
            )
            return 0

    # ── plans ─────────────────────────────────────────────────────────────────

    def _collect_plans(self) -> list[dict[str, Any]]:
        try:
            plans = paginate(self.client, "list_backup_plans", "BackupPlansList")
        except Exception as exc:
            logger.error(
                "[%s][%s] Backup plans failed: %s", self.account_name, self.region, exc
            )
            return []

        return [self._normalize_plan(p) for p in plans]

    def _normalize_plan(self, plan_summary: dict[str, Any]) -> dict[str, Any]:
        plan_id  = plan_summary.get("BackupPlanId", "")
        plan_arn = plan_summary.get("BackupPlanArn", "")
        plan_name = plan_summary.get("BackupPlanName", "")

        rules = self._get_plan_rules(plan_id)
        selections = self._get_plan_selections(plan_id)
        protected_count = sum(len(s.get("resources", [])) for s in selections)

        return {
            "resource_type":          PLAN_RESOURCE_TYPE,
            "resource_id":            plan_arn or plan_id,
            "resource_name":          plan_name,
            "account_id":             self.account_id,
            "account_name":           self.account_name,
            "region":                 self.region,
            "plan_id":                plan_id,
            "version_id":             plan_summary.get("VersionId", ""),
            "creation_date":          str(plan_summary.get("CreationDate", "")),
            "last_execution_date":    str(plan_summary.get("LastExecutionDate", "")),
            "rules":                  rules,
            "selections":             selections,
            "protected_resource_count": protected_count,
            "tags":                   {},
            "collected_at":           utc_now(),
        }

    def _get_plan_rules(self, plan_id: str) -> list[dict[str, Any]]:
        if not plan_id:
            return []
        try:
            resp = self.client.get_backup_plan(BackupPlanId=plan_id)
            rules = resp.get("BackupPlan", {}).get("Rules", [])
        except Exception as exc:
            logger.debug(
                "[%s][%s] get_backup_plan failed for %s: %s",
                self.account_name, self.region, plan_id, exc,
            )
            return []

        normalized = []
        for r in rules:
            lifecycle = r.get("Lifecycle", {}) or {}
            normalized.append({
                "rule_name":                        r.get("RuleName", ""),
                "target_vault":                     r.get("TargetBackupVaultName", ""),
                "schedule_expression":               r.get("ScheduleExpression", ""),
                "start_window_minutes":              r.get("StartWindowMinutes"),
                "completion_window_minutes":         r.get("CompletionWindowMinutes"),
                "move_to_cold_storage_after_days":   lifecycle.get("MoveToColdStorageAfterDays"),
                "delete_after_days":                 lifecycle.get("DeleteAfterDays"),
                "enable_continuous_backup":          r.get("EnableContinuousBackup", False),
            })
        return normalized

    def _get_plan_selections(self, plan_id: str) -> list[dict[str, Any]]:
        if not plan_id:
            return []
        try:
            selections = paginate(
                self.client,
                "list_backup_selections",
                "BackupSelectionsList",
                BackupPlanId=plan_id,
            )
        except Exception as exc:
            logger.debug(
                "[%s][%s] list_backup_selections failed for %s: %s",
                self.account_name, self.region, plan_id, exc,
            )
            return []

        normalized = []
        for sel_summary in selections:
            selection_id = sel_summary.get("SelectionId", "")
            detail = self._get_selection_detail(plan_id, selection_id)
            normalized.append({
                "selection_name": sel_summary.get("SelectionName", ""),
                "iam_role_arn":   detail.get("IamRoleArn", ""),
                "resources":      detail.get("Resources", []),
                "tag_conditions": detail.get("ListOfTags", []),
            })
        return normalized

    def _get_selection_detail(self, plan_id: str, selection_id: str) -> dict[str, Any]:
        if not selection_id:
            return {}
        try:
            resp = self.client.get_backup_selection(
                BackupPlanId=plan_id, SelectionId=selection_id
            )
            return resp.get("BackupSelection", {})
        except Exception as exc:
            logger.debug(
                "[%s][%s] get_backup_selection failed for %s/%s: %s",
                self.account_name, self.region, plan_id, selection_id, exc,
            )
            return {}
