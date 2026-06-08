"""
AWS EBS Volumes collector.

Collects all EBS volumes per region, including:
  - Volume metadata (size, type, state, encrypted, IOPS, throughput)
  - Attachment info (which EC2 instance + device name)
  - Tags (Name, apid, assetid, env, coid, etc.)
  - Snapshot origin

Output file: ebs.json
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::volume"


class EBSCollector:
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
        logger.info("[%s][%s] Collecting EBS Volumes", self.account_name, self.region)
        try:
            volumes = paginate(self.client, "describe_volumes", "Volumes")
            return [self._normalize(v) for v in volumes]
        except Exception as exc:
            logger.error(
                "[%s][%s] EBS Volumes failed: %s", self.account_name, self.region, exc
            )
            return []

    # ── internals ─────────────────────────────────────────────────────────────

    def _normalize(self, vol: dict[str, Any]) -> dict[str, Any]:
        volume_id   = vol["VolumeId"]
        tags        = normalize_tags(vol.get("Tags"))
        attachments = vol.get("Attachments", [])

        # Parse attachment list — a volume can technically attach to multiple
        # instances (only multi-attach volumes), but normally just one
        attached_instances: list[dict[str, str]] = []
        relationships: list[dict] = []
        for att in attachments:
            inst_id     = att.get("InstanceId", "")
            device_name = att.get("Device", "")
            state       = att.get("State", "")
            attached_instances.append({
                "instance_id": inst_id,
                "device":      device_name,
                "state":       state,
            })
            if inst_id:
                relationships.append(
                    build_relationship(
                        "aws::ec2::instance", inst_id, "attached_to_instance"
                    )
                )

        # Volume state
        state = vol.get("State", "")

        return {
            "resource_type":      RESOURCE_TYPE,
            "resource_id":        volume_id,
            "resource_name":      tags.get("Name", ""),
            "account_id":         self.account_id,
            "account_name":       self.account_name,
            "region":             self.region,
            "availability_zone":  vol.get("AvailabilityZone", ""),
            "state":              state,
            "size_gb":            vol.get("Size", 0),
            "volume_type":        vol.get("VolumeType", ""),
            "iops":               vol.get("Iops", 0),
            "throughput":         vol.get("Throughput", 0),
            "encrypted":          vol.get("Encrypted", False),
            "kms_key_id":         vol.get("KmsKeyId", ""),
            "snapshot_id":        vol.get("SnapshotId", ""),
            "multi_attach":       vol.get("MultiAttachEnabled", False),
            "create_time":        str(vol.get("CreateTime", "")),
            # attachment details
            "attached_instances": attached_instances,
            # convenience single-value fields for the common case (1 attachment)
            "attached_instance_id":   attached_instances[0]["instance_id"] if attached_instances else "",
            "attached_device":        attached_instances[0]["device"]      if attached_instances else "",
            "attached_state":         attached_instances[0]["state"]       if attached_instances else "",
            "tags":                   tags,
            "relationships":          relationships,
            "collected_at":           utc_now(),
        }
