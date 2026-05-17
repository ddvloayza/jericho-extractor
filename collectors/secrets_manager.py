from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::secretsmanager::secret"


class SecretsManagerCollector:
    """Collect Secrets Manager secrets — metadata ONLY, never secret values."""

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
        logger.info("[%s][%s] Collecting Secrets Manager secrets", self.account_name, self.region)
        try:
            secrets = paginate(self.client, "list_secrets", "SecretList")
            return [self._normalize(s) for s in secrets]
        except Exception as exc:
            logger.error(
                "[%s][%s] Secrets Manager failed: %s", self.account_name, self.region, exc
            )
            return []

    def _normalize(self, secret: dict[str, Any]) -> dict[str, Any]:
        arn         = secret["ARN"]
        kms_key_id  = secret.get("KmsKeyId", "")

        relationships: list[dict[str, str]] = []
        if kms_key_id:
            relationships.append(build_relationship("aws::kms::key", kms_key_id, "encrypted_by_kms"))

        tags = {t["Key"]: t["Value"] for t in secret.get("Tags") or []}

        return {
            "resource_type":        RESOURCE_TYPE,
            "resource_id":          arn,
            "resource_name":        secret.get("Name", ""),
            "account_id":           self.account_id,
            "account_name":         self.account_name,
            "region":               self.region,
            "description":          secret.get("Description", ""),
            "kms_key_id":           kms_key_id,
            "rotation_enabled":     secret.get("RotationEnabled", False),
            "rotation_lambda_arn":  secret.get("RotationLambdaARN", ""),
            "last_changed_date":    str(secret.get("LastChangedDate", "")),
            "last_accessed_date":   str(secret.get("LastAccessedDate", "")),
            "last_rotated_date":    str(secret.get("LastRotatedDate", "")),
            "created_date":         str(secret.get("CreatedDate", "")),
            "deleted_date":         str(secret.get("DeletedDate", "")) if secret.get("DeletedDate") else "",
            "owning_service":       secret.get("OwningService", ""),
            "tags":                 tags,
            "relationships":        relationships,
            "collected_at":         utc_now(),
        }
