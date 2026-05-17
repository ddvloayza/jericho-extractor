from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::lambda::function"


class LambdaCollector:
    """Collect AWS Lambda functions with networking, IAM, and encryption metadata."""

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
        logger.info("[%s][%s] Collecting Lambda functions", self.account_name, self.region)
        try:
            functions = paginate(self.client, "list_functions", "Functions")
            return [self._normalize(fn) for fn in functions]
        except Exception as exc:
            logger.error(
                "[%s][%s] Lambda functions failed: %s", self.account_name, self.region, exc
            )
            return []

    def _normalize(self, fn: dict[str, Any]) -> dict[str, Any]:
        arn         = fn["FunctionArn"]
        vpc_config  = fn.get("VpcConfig") or {}
        vpc_id      = vpc_config.get("VpcId", "")
        subnet_ids  = vpc_config.get("SubnetIds") or []
        sg_ids      = vpc_config.get("SecurityGroupIds") or []
        role_arn    = fn.get("Role", "")
        kms_key_arn = fn.get("KMSKeyArn", "")

        dlq = fn.get("DeadLetterConfig") or {}
        tracing = fn.get("TracingConfig") or {}

        env_keys: list[str] = []
        if env := fn.get("Environment"):
            env_keys = list((env.get("Variables") or {}).keys())

        relationships: list[dict[str, str]] = []
        for sid in subnet_ids:
            relationships.append(build_relationship("aws::ec2::subnet", sid, "deployed_in_subnet"))
        for sg_id in sg_ids:
            relationships.append(build_relationship("aws::ec2::security_group", sg_id, "protected_by_sg"))
        if role_arn:
            relationships.append(build_relationship("aws::iam::role", role_arn, "uses_iam_role"))
        if kms_key_arn:
            relationships.append(build_relationship("aws::kms::key", kms_key_arn, "encrypted_by_kms"))

        tags = self._fetch_tags(arn)

        return {
            "resource_type":      RESOURCE_TYPE,
            "resource_id":        arn,
            "resource_name":      fn.get("FunctionName", ""),
            "account_id":         self.account_id,
            "account_name":       self.account_name,
            "region":             self.region,
            "runtime":            fn.get("Runtime", ""),
            "memory_mb":          fn.get("MemorySize", 0),
            "timeout_seconds":    fn.get("Timeout", 0),
            "architectures":      fn.get("Architectures") or [],
            "last_modified":      fn.get("LastModified", ""),
            "code_size_bytes":    fn.get("CodeSize", 0),
            "handler":            fn.get("Handler", ""),
            "description":        fn.get("Description", ""),
            "vpc_id":             vpc_id,
            "subnet_ids":         subnet_ids,
            "security_group_ids": sg_ids,
            "execution_role":     role_arn,
            "kms_key_arn":        kms_key_arn,
            "environment_keys":   env_keys,
            "tracing_mode":       tracing.get("Mode", ""),
            "dead_letter_target": dlq.get("TargetArn", ""),
            "tags":               tags,
            "relationships":      relationships,
            "collected_at":       utc_now(),
        }

    def _fetch_tags(self, arn: str) -> dict[str, str]:
        try:
            return self.client.list_tags(Resource=arn).get("Tags") or {}
        except Exception:
            return {}
