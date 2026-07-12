"""
GuardDuty collector.

Output file: guardduty.json

Required IAM permissions (read-only):
  guardduty:ListDetectors
  guardduty:GetDetector
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::guardduty::detector"


class GuardDutyCollector:
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
        logger.info("[%s][%s] Collecting GuardDuty detectors", self.account_name, self.region)
        try:
            detector_ids = paginate(self.client, "list_detectors", "DetectorIds")
        except Exception as exc:
            logger.error("[%s][%s] GuardDuty failed: %s", self.account_name, self.region, exc)
            return []

        results = []
        for det_id in detector_ids:
            record = self._describe(det_id)
            if record:
                results.append(record)
        return results

    def _describe(self, detector_id: str) -> dict[str, Any] | None:
        try:
            detail = self.client.get_detector(DetectorId=detector_id)
        except Exception as exc:
            logger.debug("[%s][%s] get_detector failed for %s: %s",
                         self.account_name, self.region, detector_id, exc)
            return None

        data_sources = detail.get("DataSources", {}) or {}
        return {
            "resource_type":               RESOURCE_TYPE,
            "resource_id":                 detector_id,
            "resource_name":               detector_id,
            "account_id":                  self.account_id,
            "account_name":                self.account_name,
            "region":                      self.region,
            "status":                      detail.get("Status", ""),   # ENABLED / DISABLED
            "finding_publishing_frequency": detail.get("FindingPublishingFrequency", ""),
            "service_role":                detail.get("ServiceRole", ""),
            "s3_logs_enabled":             (data_sources.get("S3Logs", {}) or {}).get("Status", "") == "ENABLED",
            "kubernetes_audit_logs_enabled": (data_sources.get("Kubernetes", {}).get("AuditLogs", {}) or {}).get("Status", "") == "ENABLED",
            "malware_protection_enabled":  bool(data_sources.get("MalwareProtection")),
            "created_at":                  str(detail.get("CreatedAt", "")),
            "updated_at":                  str(detail.get("UpdatedAt", "")),
            "tags":                        detail.get("Tags", {}) or {},
            "collected_at":                utc_now(),
        }
