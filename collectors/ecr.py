"""
Elastic Container Registry (ECR) collector.

EKS workloads pull their images from somewhere — this covers the
repositories and image storage that back those Kubernetes deployments.

Output file: ecr.json

Required IAM permissions (read-only):
  ecr:DescribeRepositories
  ecr:DescribeImages
  ecr:ListTagsForResource

Pricing reference: $0.10/GB-month for private image storage
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ecr::repository"

_STORAGE_PRICE_PER_GB = 0.10


class ECRCollector:
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
        logger.info("[%s][%s] Collecting ECR repositories", self.account_name, self.region)
        try:
            repos = paginate(self.client, "describe_repositories", "repositories")
        except Exception as exc:
            logger.error("[%s][%s] ECR repositories failed: %s", self.account_name, self.region, exc)
            return []

        return [self._normalize(r) for r in repos]

    def _normalize(self, repo: dict[str, Any]) -> dict[str, Any]:
        name = repo.get("repositoryName", "")
        arn  = repo.get("repositoryArn", "")
        image_count, total_bytes = self._image_stats(name)
        size_gb = round(total_bytes / (1024 ** 3), 4)

        return {
            "resource_type":       RESOURCE_TYPE,
            "resource_id":         arn or name,
            "resource_name":       name,
            "account_id":          self.account_id,
            "account_name":        self.account_name,
            "region":              self.region,
            "created_at":          str(repo.get("createdAt", "")),
            "image_tag_mutability": repo.get("imageTagMutability", ""),
            "scan_on_push":        repo.get("imageScanningConfiguration", {}).get("scanOnPush", False),
            "encryption_type":     repo.get("encryptionConfiguration", {}).get("encryptionType", "AES256"),
            "image_count":         image_count,
            "total_size_bytes":    total_bytes,
            "total_size_gb":       size_gb,
            "est_cost_per_month":  round(size_gb * _STORAGE_PRICE_PER_GB, 4),
            "tags":                self._get_tags(arn),
            "collected_at":        utc_now(),
        }

    def _image_stats(self, repo_name: str) -> tuple[int, int]:
        try:
            images = paginate(
                self.client, "describe_images", "imageDetails",
                repositoryName=repo_name,
            )
            total_bytes = sum(img.get("imageSizeInBytes", 0) or 0 for img in images)
            return len(images), total_bytes
        except Exception as exc:
            logger.debug("[%s][%s] describe_images failed for %s: %s",
                         self.account_name, self.region, repo_name, exc)
            return 0, 0

    def _get_tags(self, arn: str) -> dict[str, str]:
        if not arn:
            return {}
        try:
            tags = self.client.list_tags_for_resource(resourceArn=arn).get("tags", [])
            return {t["Key"]: t.get("Value", "") for t in tags}
        except Exception:
            return {}
