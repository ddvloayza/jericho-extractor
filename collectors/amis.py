"""
AWS AMI (Amazon Machine Image) collector.

Collects all AMIs owned by this account, including:
  - Image metadata (ID, name, description, creation date, age)
  - Architecture, platform, virtualization type
  - Root device type and snapshot IDs embedded in block device mappings
  - State (available / pending / failed)

Output file: amis.json

Note: AMI cost in CE shows up as "EC2 - Other" tagged with the AMI's Name tag.
      The actual storage cost comes from the EBS snapshots that back the AMI.
      Deregistering an AMI does NOT delete the backing snapshots — must delete separately.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, utc_now

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::ami"


class AMICollector:
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
            "[%s][%s] Collecting AMIs (owned by this account)",
            self.account_name, self.region,
        )
        try:
            resp = self.client.describe_images(Owners=["self"])
            images = resp.get("Images", [])
            logger.info(
                "[%s][%s] AMIs found: %d", self.account_name, self.region, len(images)
            )
            return [self._normalize(img) for img in images]
        except Exception as exc:
            logger.error(
                "[%s][%s] AMIs failed: %s", self.account_name, self.region, exc
            )
            return []

    # ── internals ─────────────────────────────────────────────────────────────

    def _normalize(self, img: dict[str, Any]) -> dict[str, Any]:
        image_id     = img["ImageId"]
        tags         = normalize_tags(img.get("Tags"))
        creation_raw = img.get("CreationDate", "")

        # Parse creation date and compute age
        age_days: int | None = None
        if creation_raw:
            try:
                # AWS returns ISO 8601: "2026-02-20T14:30:00.000Z"
                dt = datetime.fromisoformat(creation_raw.replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - dt).days
            except Exception:
                pass

        # Extract snapshot IDs from block device mappings
        bdm_snapshots: list[dict[str, Any]] = []
        total_size_gb = 0
        for bdm in img.get("BlockDeviceMappings", []):
            ebs = bdm.get("Ebs", {})
            snap_id = ebs.get("SnapshotId", "")
            size_gb = ebs.get("VolumeSize", 0)
            vol_type = ebs.get("VolumeType", "")
            device   = bdm.get("DeviceName", "")
            if snap_id or size_gb:
                bdm_snapshots.append({
                    "device":      device,
                    "snapshot_id": snap_id,
                    "size_gb":     size_gb,
                    "volume_type": vol_type,
                })
                total_size_gb += size_gb

        # Estimated monthly storage cost (all backing snapshots)
        est_cost_month = round(total_size_gb * 0.05, 4)

        return {
            "resource_type":      RESOURCE_TYPE,
            "resource_id":        image_id,
            "resource_name":      img.get("Name", "") or tags.get("Name", ""),
            "account_id":         self.account_id,
            "account_name":       self.account_name,
            "region":             self.region,
            "state":              img.get("State", ""),
            "name":               img.get("Name", ""),
            "description":        img.get("Description", ""),
            "architecture":       img.get("Architecture", ""),
            "platform":           img.get("Platform", "linux"),    # "windows" or blank
            "virtualization":     img.get("VirtualizationType", ""),
            "root_device_type":   img.get("RootDeviceType", ""),
            "root_device_name":   img.get("RootDeviceName", ""),
            "public":             img.get("Public", False),
            "creation_date":      creation_raw,
            "age_days":           age_days,
            "total_size_gb":      total_size_gb,
            "est_cost_per_month": est_cost_month,
            "snapshots":          bdm_snapshots,
            "snapshot_ids":       [s["snapshot_id"] for s in bdm_snapshots if s["snapshot_id"]],
            "tags":               tags,
            "collected_at":       utc_now(),
        }
