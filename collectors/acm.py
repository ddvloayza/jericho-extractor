"""
AWS Certificate Manager (ACM) collector.

Output file: acm.json

Required IAM permissions (read-only):
  acm:ListCertificates
  acm:DescribeCertificate
  acm:ListTagsForCertificate
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::acm::certificate"


class ACMCollector:
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
        logger.info("[%s][%s] Collecting ACM certificates", self.account_name, self.region)
        try:
            certs = paginate(self.client, "list_certificates", "CertificateSummaryList")
        except Exception as exc:
            logger.error("[%s][%s] ACM certificates failed: %s", self.account_name, self.region, exc)
            return []

        results = []
        for c in certs:
            record = self._describe(c.get("CertificateArn", ""))
            if record:
                results.append(record)
        return results

    def _describe(self, arn: str) -> dict[str, Any] | None:
        if not arn:
            return None
        try:
            cert = self.client.describe_certificate(CertificateArn=arn).get("Certificate", {})
        except Exception as exc:
            logger.debug("[%s][%s] describe_certificate failed for %s: %s",
                         self.account_name, self.region, arn, exc)
            return None

        in_use_by = cert.get("InUseBy", []) or []

        return {
            "resource_type":     RESOURCE_TYPE,
            "resource_id":       arn,
            "resource_name":     cert.get("DomainName", ""),
            "account_id":        self.account_id,
            "account_name":      self.account_name,
            "region":            self.region,
            "status":            cert.get("Status", ""),
            "type":              cert.get("Type", ""),   # AMAZON_ISSUED / IMPORTED
            "key_algorithm":     cert.get("KeyAlgorithm", ""),
            "not_before":        str(cert.get("NotBefore", "")),
            "not_after":         str(cert.get("NotAfter", "")),
            "subject_alternative_names": cert.get("SubjectAlternativeNames", []),
            "in_use":            bool(in_use_by),
            "in_use_by":         in_use_by,
            "renewal_eligibility": cert.get("RenewalEligibility", ""),
            "tags":              self._get_tags(arn),
            "collected_at":      utc_now(),
        }

    def _get_tags(self, arn: str) -> dict[str, str]:
        try:
            tags = self.client.list_tags_for_certificate(CertificateArn=arn).get("Tags", [])
            return {t["Key"]: t.get("Value", "") for t in tags}
        except Exception:
            return {}
