from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::kms::key"


class KMSCollector:
    """Collect KMS keys with aliases, rotation status, and metadata."""

    def __init__(
        self,
        client: BaseClient,
        account_id: str,
        account_name: str,
        region: str,
    ) -> None:
        self.client = client
        self.account_id = account_id
        self.account_name = account_name
        self.region = region

    def collect(self) -> list[dict[str, Any]]:
        logger.info("[%s][%s] Collecting KMS keys", self.account_name, self.region)
        try:
            keys = paginate(self.client, "list_keys", "Keys")
            results = []
            for key_ref in keys:
                normalized = self._describe_and_normalize(key_ref["KeyId"])
                if normalized:
                    results.append(normalized)
            return results
        except Exception as exc:
            logger.error(
                "[%s][%s] KMS keys failed: %s", self.account_name, self.region, exc
            )
            return []

    def _describe_and_normalize(self, key_id: str) -> dict[str, Any] | None:
        try:
            meta = self.client.describe_key(KeyId=key_id)["KeyMetadata"]
        except Exception as exc:
            logger.debug("describe_key failed for %s: %s", key_id, exc)
            return None

        key_arn     = meta["Arn"]
        key_manager = meta.get("KeyManager", "")
        key_state   = meta.get("KeyState", "")

        aliases = self._list_aliases(key_id)
        rotation_enabled = self._get_rotation_status(key_id, key_manager)
        tags = self._fetch_tags(key_arn)

        return {
            "resource_type":       RESOURCE_TYPE,
            "resource_id":         key_arn,
            "resource_name":       aliases[0] if aliases else key_id,
            "account_id":          self.account_id,
            "account_name":        self.account_name,
            "region":              self.region,
            "key_id":              key_id,
            "key_state":           key_state,
            "key_usage":           meta.get("KeyUsage", ""),
            "key_spec":            meta.get("KeySpec", ""),
            "key_manager":         key_manager,
            "enabled":             meta.get("Enabled", False),
            "multi_region":        meta.get("MultiRegion", False),
            "multi_region_key_type": meta.get("MultiRegionConfiguration", {}).get("MultiRegionKeyType", ""),
            "description":         meta.get("Description", ""),
            "creation_date":       str(meta.get("CreationDate", "")),
            "deletion_date":       str(meta.get("DeletionDate", "")) if meta.get("DeletionDate") else "",
            "rotation_enabled":    rotation_enabled,
            "aliases":             aliases,
            "origin":              meta.get("Origin", ""),
            "tags":                tags,
            "relationships":       [],
            "collected_at":        utc_now(),
        }

    def _list_aliases(self, key_id: str) -> list[str]:
        try:
            aliases = paginate(self.client, "list_aliases", "Aliases", KeyId=key_id)
            return [a["AliasName"] for a in aliases if a.get("AliasName")]
        except Exception:
            return []

    def _get_rotation_status(self, key_id: str, key_manager: str) -> bool:
        # AWS-managed keys cannot have rotation queried the same way
        if key_manager == "AWS":
            return True
        try:
            return self.client.get_key_rotation_status(KeyId=key_id).get("KeyRotationEnabled", False)
        except Exception:
            return False

    def _fetch_tags(self, key_arn: str) -> dict[str, str]:
        try:
            tags = paginate(self.client, "list_resource_tags", "Tags", KeyId=key_arn)
            return {t["TagKey"]: t["TagValue"] for t in tags}
        except Exception:
            return {}
