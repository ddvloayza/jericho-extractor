from __future__ import annotations

import logging
from typing import Any

import boto3
from botocore.client import BaseClient

from utils.helpers import utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::s3::bucket"


class S3Collector:
    """Collect S3 buckets with encryption, access, versioning, and logging metadata.

    S3 is a global service — buckets are enumerated once per account and their
    region is resolved individually. Pass the default-region session client;
    per-bucket clients are created on demand for location-aware API calls.
    """

    def __init__(
        self,
        client: BaseClient,
        session: boto3.Session,
        account_id: str,
        account_name: str,
    ) -> None:
        self.client = client
        self.session = session
        self.account_id = account_id
        self.account_name = account_name

    def collect(self) -> list[dict[str, Any]]:
        logger.info("[%s][global] Collecting S3 buckets", self.account_name)
        try:
            buckets = self.client.list_buckets().get("Buckets") or []
            return [r for b in buckets if (r := self._normalize(b)) is not None]
        except Exception as exc:
            logger.error("[%s][global] S3 buckets failed: %s", self.account_name, exc)
            return []

    def _normalize(self, bucket: dict[str, Any]) -> dict[str, Any] | None:
        name = bucket["Name"]
        try:
            region = self._get_region(name)
            # Use a regional client for all subsequent calls to avoid redirect errors
            rc = self.session.client("s3", region_name=region or "us-east-1")

            encryption, kms_key_id = self._get_encryption(rc, name)
            public_access_block    = self._get_public_access_block(rc, name)
            policy_public          = self._get_policy_status(rc, name)
            versioning             = self._get_versioning(rc, name)
            logging_enabled        = self._get_logging(rc, name)
            acl_public             = self._get_acl_public(rc, name)
            tags                   = self._get_tags(rc, name)

            relationships: list[dict[str, str]] = []
            if kms_key_id:
                relationships.append(build_relationship("aws::kms::key", kms_key_id, "encrypted_by_kms"))

            return {
                "resource_type":         RESOURCE_TYPE,
                "resource_id":           f"arn:aws:s3:::{name}",
                "resource_name":         name,
                "account_id":            self.account_id,
                "account_name":          self.account_name,
                "region":                region or "us-east-1",
                "creation_date":         str(bucket.get("CreationDate", "")),
                "encryption_type":       encryption,
                "kms_key_id":            kms_key_id,
                "versioning_status":     versioning,
                "logging_enabled":       logging_enabled,
                "acl_public":            acl_public,
                "bucket_policy_public":  policy_public,
                "block_public_acls":     public_access_block.get("BlockPublicAcls", False),
                "ignore_public_acls":    public_access_block.get("IgnorePublicAcls", False),
                "block_public_policy":   public_access_block.get("BlockPublicPolicy", False),
                "restrict_public_buckets": public_access_block.get("RestrictPublicBuckets", False),
                "tags":                  tags,
                "relationships":         relationships,
                "collected_at":          utc_now(),
            }
        except Exception as exc:
            logger.error("[%s] S3 bucket %s failed: %s", self.account_name, name, exc)
            return None

    def _get_region(self, name: str) -> str:
        try:
            loc = self.client.get_bucket_location(Bucket=name).get("LocationConstraint")
            # us-east-1 returns None from LocationConstraint
            return loc or "us-east-1"
        except Exception:
            return "us-east-1"

    def _get_encryption(self, client: BaseClient, name: str) -> tuple[str, str]:
        try:
            rules = client.get_bucket_encryption(Bucket=name)
            rules = rules["ServerSideEncryptionConfiguration"]["Rules"]
            if not rules:
                return ("None", "")
            rule = rules[0].get("ApplyServerSideEncryptionByDefault") or {}
            algo = rule.get("SSEAlgorithm", "")
            kms  = rule.get("KMSMasterKeyID", "")
            return (algo, kms)
        except client.exceptions.ClientError as exc:
            if exc.response["Error"]["Code"] == "ServerSideEncryptionConfigurationNotFoundError":
                return ("None", "")
            return ("unknown", "")
        except Exception:
            return ("unknown", "")

    def _get_public_access_block(self, client: BaseClient, name: str) -> dict[str, bool]:
        try:
            return client.get_public_access_block(Bucket=name).get("PublicAccessBlockConfiguration") or {}
        except Exception:
            return {}

    def _get_policy_status(self, client: BaseClient, name: str) -> bool:
        try:
            return client.get_bucket_policy_status(Bucket=name).get(
                "PolicyStatus", {}
            ).get("IsPublic", False)
        except Exception:
            return False

    def _get_versioning(self, client: BaseClient, name: str) -> str:
        try:
            return client.get_bucket_versioning(Bucket=name).get("Status", "Disabled") or "Disabled"
        except Exception:
            return "unknown"

    def _get_logging(self, client: BaseClient, name: str) -> bool:
        try:
            cfg = client.get_bucket_logging(Bucket=name).get("LoggingEnabled")
            return cfg is not None
        except Exception:
            return False

    def _get_acl_public(self, client: BaseClient, name: str) -> bool:
        try:
            grants = client.get_bucket_acl(Bucket=name).get("Grants") or []
            public_uris = {
                "http://acs.amazonaws.com/groups/global/AllUsers",
                "http://acs.amazonaws.com/groups/global/AuthenticatedUsers",
            }
            return any(
                g.get("Grantee", {}).get("URI") in public_uris
                for g in grants
            )
        except Exception:
            return False

    def _get_tags(self, client: BaseClient, name: str) -> dict[str, str]:
        try:
            tags = client.get_bucket_tagging(Bucket=name).get("TagSet") or []
            return {t["Key"]: t["Value"] for t in tags}
        except Exception:
            return {}
