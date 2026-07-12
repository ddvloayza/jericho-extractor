"""
Route53 collector — hosted zones and health checks.

Route53 is a global service; region is always 'global' for output consistency.

Output file: route53.json  (mixed resource_type: hostedzone + healthcheck)

Required IAM permissions (read-only):
  route53:ListHostedZones
  route53:ListTagsForResource
  route53:ListHealthChecks
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now

logger = logging.getLogger(__name__)

ZONE_RESOURCE_TYPE = "aws::route53::hostedzone"
HEALTH_RESOURCE_TYPE = "aws::route53::healthcheck"


class Route53Collector:
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
        logger.info("[%s][global] Collecting Route53 hosted zones + health checks", self.account_name)
        results: list[dict[str, Any]] = []
        results.extend(self._collect_zones())
        results.extend(self._collect_health_checks())
        return results

    def _collect_zones(self) -> list[dict[str, Any]]:
        try:
            zones = paginate(self.client, "list_hosted_zones", "HostedZones")
        except Exception as exc:
            logger.error("[%s][global] Route53 zones failed: %s", self.account_name, exc)
            return []
        return [self._normalize_zone(z) for z in zones]

    def _normalize_zone(self, zone: dict[str, Any]) -> dict[str, Any]:
        zone_id = zone.get("Id", "").replace("/hostedzone/", "")
        name    = zone.get("Name", "")
        config  = zone.get("Config", {}) or {}

        return {
            "resource_type":       ZONE_RESOURCE_TYPE,
            "resource_id":         zone_id,
            "resource_name":       name,
            "account_id":          self.account_id,
            "account_name":        self.account_name,
            "region":              "global",
            "is_private":          config.get("PrivateZone", False),
            "record_set_count":    zone.get("ResourceRecordSetCount", 0),
            "comment":             config.get("Comment", ""),
            "tags":                self._get_zone_tags(zone_id),
            "collected_at":        utc_now(),
        }

    def _get_zone_tags(self, zone_id: str) -> dict[str, str]:
        try:
            resp = self.client.list_tags_for_resource(ResourceType="hostedzone", ResourceId=zone_id)
            tags = resp.get("ResourceTagSet", {}).get("Tags", [])
            return {t["Key"]: t.get("Value", "") for t in tags}
        except Exception:
            return {}

    def _collect_health_checks(self) -> list[dict[str, Any]]:
        try:
            checks = paginate(self.client, "list_health_checks", "HealthChecks")
        except Exception as exc:
            logger.error("[%s][global] Route53 health checks failed: %s", self.account_name, exc)
            return []
        return [self._normalize_health_check(c) for c in checks]

    def _normalize_health_check(self, check: dict[str, Any]) -> dict[str, Any]:
        check_id = check.get("Id", "")
        cfg = check.get("HealthCheckConfig", {}) or {}

        return {
            "resource_type":  HEALTH_RESOURCE_TYPE,
            "resource_id":    check_id,
            "resource_name":  check_id,
            "account_id":     self.account_id,
            "account_name":   self.account_name,
            "region":         "global",
            "type":           cfg.get("Type", ""),
            "fqdn":           cfg.get("FullyQualifiedDomainName", ""),
            "port":           cfg.get("Port"),
            "resource_path":  cfg.get("ResourcePath", ""),
            "tags":           {},
            "collected_at":   utc_now(),
        }
