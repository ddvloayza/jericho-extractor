"""
AWS EBS Snapshots collector.

Collects all EBS snapshots owned by this account, including:
  - Snapshot metadata (ID, size, state, age)
  - Source volume ID (to cross-reference with ebs.json)
  - Tags (Name, apid, env, etc.)
  - Whether the source volume still exists (populated by main.py enrichment)

Output file: snapshots.json

Pricing reference (approx):  ~$0.05/GB-month (standard),  ~$0.0125/GB-month (archive)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::snapshot"

# Approximate EBS snapshot pricing per GB/month (standard tier)
_SNAPSHOT_PRICE_PER_GB = 0.05


class SnapshotCollector:
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
            "[%s][%s] Collecting EBS Snapshots (owned by this account)",
            self.account_name, self.region,
        )
        try:
            snapshots = paginate(
                self.client,
                "describe_snapshots",
                "Snapshots",
                OwnerIds=["self"],
            )
            return [self._normalize(s) for s in snapshots]
        except Exception as exc:
            logger.error(
                "[%s][%s] EBS Snapshots failed: %s", self.account_name, self.region, exc
            )
            return []

    # ── internals ─────────────────────────────────────────────────────────────

    def _normalize(self, snap: dict[str, Any]) -> dict[str, Any]:
        snap_id   = snap["SnapshotId"]
        tags      = normalize_tags(snap.get("Tags"))
        size_gb   = snap.get("VolumeSize", 0)
        start_raw = snap.get("StartTime")

        # Parse start_time and compute age
        if start_raw:
            if hasattr(start_raw, "isoformat"):
                start_str = start_raw.isoformat()
                start_dt  = start_raw if start_raw.tzinfo else start_raw.replace(tzinfo=timezone.utc)
            else:
                start_str = str(start_raw)
                start_dt  = None
        else:
            start_str = ""
            start_dt  = None

        age_days: int | None = None
        if start_dt:
            now     = datetime.now(timezone.utc)
            age_days = (now - start_dt).days

        # Estimated cost: snapshots are incremental but we use size as upper-bound proxy
        est_cost_month = round(size_gb * _SNAPSHOT_PRICE_PER_GB, 4)

        return {
            "resource_type":      RESOURCE_TYPE,
            "resource_id":        snap_id,
            "resource_name":      tags.get("Name", ""),
            "account_id":         self.account_id,
            "account_name":       self.account_name,
            "region":             self.region,
            "state":              snap.get("State", ""),
            "progress":           snap.get("Progress", ""),
            "description":        snap.get("Description", ""),
            "volume_id":          snap.get("VolumeId", ""),
            "volume_size_gb":     size_gb,
            "encrypted":          snap.get("Encrypted", False),
            "kms_key_id":         snap.get("KmsKeyId", ""),
            "storage_tier":       snap.get("StorageTier", "standard"),
            "start_time":         start_str,
            "age_days":           age_days,
            # cost estimation (upper bound — real cost depends on incremental delta)
            "est_cost_per_month": est_cost_month,
            # enriched later by main.py after EBS collection
            "volume_exists":      None,   # True/False/None
            "volume_name":        "",
            "attached_ec2_name":  "",
            "ami_ids":            [],     # filled by main.py if snapshot backs an AMI
            "tags":               tags,
            "collected_at":       utc_now(),
        }
