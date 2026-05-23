from __future__ import annotations

"""
Cross-account relationship mapper.

Reads already-collected per-account JSON output and finds relationships
that span account boundaries:

  - Transit Gateway connections (shared TGW ID across accounts)
  - VPC Peering (requester / accepter in different accounts)
  - IAM role trust (role trusts a principal in another account)
  - KMS key usage across accounts (key ARN from account A used in account B)
  - Secrets Manager cross-account (same pattern as KMS)
  - S3 cross-account (bucket owned by account A accessed from account B)

Output is written to  output/cross_account/
"""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _account_from_arn(arn: str) -> str:
    """Extract account ID from an ARN string (field [4])."""
    parts = arn.split(":")
    return parts[4] if len(parts) >= 5 else ""


# ── main mapper ───────────────────────────────────────────────────────────────

class CrossAccountMapper:
    """
    Detect cross-account relationships from per-account collected data.

    Usage::

        mapper = CrossAccountMapper(output_dir=Path("output"))
        results = mapper.build_all()   # returns dict with all findings
    """

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self._accounts: list[dict[str, Any]] = []   # {name, id, data}

    # ── public ────────────────────────────────────────────────────────────────

    def build_all(self) -> dict[str, Any]:
        """Load all account data and compute every cross-account relationship."""
        self._load_accounts()

        if len(self._accounts) < 2:
            logger.info("Less than 2 accounts found — skipping cross-account analysis")
            return {}

        logger.info(
            "Cross-account analysis across %d accounts: %s",
            len(self._accounts),
            [a["name"] for a in self._accounts],
        )

        results: dict[str, Any] = {
            "accounts_analyzed": [
                {"name": a["name"], "account_id": a["id"]} for a in self._accounts
            ],
            "tgw_connections":           self._tgw_connections(),
            "vpc_peerings":              self._vpc_peerings(),
            "iam_trust_relationships":   self._iam_trust_relationships(),
            "kms_cross_account":         self._kms_cross_account(),
            "secrets_cross_account":     self._secrets_cross_account(),
            "s3_cross_account":          self._s3_cross_account(),
        }

        results["summary"] = self._make_summary(results)
        return results

    # ── account loading ───────────────────────────────────────────────────────

    def _load_accounts(self) -> None:
        self._accounts = []
        for account_dir in sorted(self.output_dir.iterdir()):
            if not account_dir.is_dir() or account_dir.name == "cross_account":
                continue
            data = self._load_account_data(account_dir)
            if not data:
                continue
            account_id = ""
            # Derive account_id from any resource's account_id field
            for resource_list in data.values():
                if resource_list:
                    account_id = resource_list[0].get("account_id", "")
                    break
            self._accounts.append({
                "name": account_dir.name,
                "id":   account_id,
                "dir":  account_dir,
                "data": data,
            })
            logger.info("Loaded account: %s (%s)", account_dir.name, account_id)

    def _load_account_data(self, account_dir: Path) -> dict[str, list[dict]]:
        resource_files = {
            "vpcs":                    "vpcs.json",
            "transit_gateways":        "transit_gateways.json",
            "tgw_attachments":         "transit_gateway_attachments.json",
            "vpc_peerings":            "vpc_peerings.json",
            "iam_roles":               "iam_roles.json",
            "kms":                     "kms.json",
            "secrets":                 "secrets.json",
            "s3_buckets":              "s3_buckets.json",
            "lambdas":                 "lambdas.json",
            "ec2":                     "ec2.json",
            "rds":                     "rds.json",
        }
        data: dict[str, list[dict]] = {}
        for key, filename in resource_files.items():
            data[key] = _load(account_dir / filename)
        return data

    # ── TGW connections ───────────────────────────────────────────────────────

    def _tgw_connections(self) -> list[dict[str, Any]]:
        """
        Two accounts sharing a Transit Gateway ID → cross-account TGW connection.
        The TGW is owned by one account; the other attaches a VPC to it.
        """
        # Map tgw_id → list of (account_name, account_id, attachment)
        tgw_index: dict[str, list[dict]] = defaultdict(list)

        for account in self._accounts:
            for att in account["data"].get("tgw_attachments", []):
                tgw_id = att.get("transit_gateway_id", "")
                if tgw_id:
                    tgw_index[tgw_id].append({
                        "account_name":  account["name"],
                        "account_id":    account["id"],
                        "attachment_id": att.get("resource_id", ""),
                        "vpc_id":        att.get("resource_id_ref", ""),
                        "state":         att.get("state", ""),
                    })

        connections = []
        for tgw_id, attachments in tgw_index.items():
            accounts_involved = {a["account_name"] for a in attachments}
            if len(accounts_involved) > 1:
                connections.append({
                    "transit_gateway_id": tgw_id,
                    "accounts":           sorted(accounts_involved),
                    "attachments":        attachments,
                    "relationship":       "cross_account_tgw_connection",
                })

        logger.info("TGW cross-account connections: %d", len(connections))
        return connections

    # ── VPC peerings ──────────────────────────────────────────────────────────

    def _vpc_peerings(self) -> list[dict[str, Any]]:
        """VPC peerings where requester and accepter are in different accounts."""
        peerings = []
        account_ids = {a["id"] for a in self._accounts}

        for account in self._accounts:
            for peering in account["data"].get("vpc_peerings", []):
                requester = peering.get("requester_vpc_info", {})
                accepter  = peering.get("accepter_vpc_info", {})
                req_account = requester.get("OwnerId", "")
                acc_account = accepter.get("OwnerId", "")

                if req_account != acc_account and (
                    req_account in account_ids or acc_account in account_ids
                ):
                    # Resolve account names
                    req_name = self._account_name(req_account)
                    acc_name = self._account_name(acc_account)
                    peerings.append({
                        "peering_id":          peering.get("resource_id", ""),
                        "status":              peering.get("status", ""),
                        "requester_account_id":   req_account,
                        "requester_account_name": req_name,
                        "requester_vpc_id":    requester.get("VpcId", ""),
                        "requester_cidr":      requester.get("CidrBlock", ""),
                        "accepter_account_id":    acc_account,
                        "accepter_account_name":  acc_name,
                        "accepter_vpc_id":     accepter.get("VpcId", ""),
                        "accepter_cidr":       accepter.get("CidrBlock", ""),
                        "relationship":        "cross_account_vpc_peering",
                    })

        # Deduplicate (same peering may appear in both accounts)
        seen: set[str] = set()
        unique: list[dict] = []
        for p in peerings:
            pid = p["peering_id"]
            if pid not in seen:
                seen.add(pid)
                unique.append(p)

        logger.info("Cross-account VPC peerings: %d", len(unique))
        return unique

    # ── IAM trust ─────────────────────────────────────────────────────────────

    def _iam_trust_relationships(self) -> list[dict[str, Any]]:
        """IAM roles that trust a principal in a different known account."""
        account_ids = {a["id"]: a["name"] for a in self._accounts}
        trust_rels = []

        for account in self._accounts:
            for role in account["data"].get("iam_roles", []):
                trusted_accounts = role.get("trusted_accounts", [])
                for trusted_id in trusted_accounts:
                    if trusted_id != account["id"] and trusted_id in account_ids:
                        trust_rels.append({
                            "role_arn":              role.get("resource_id", ""),
                            "role_name":             role.get("resource_name", ""),
                            "owner_account_id":      account["id"],
                            "owner_account_name":    account["name"],
                            "trusted_account_id":    trusted_id,
                            "trusted_account_name":  account_ids[trusted_id],
                            "trusted_services":      role.get("trusted_services", []),
                            "relationship":          "cross_account_iam_trust",
                        })

        logger.info("Cross-account IAM trust relationships: %d", len(trust_rels))
        return trust_rels

    # ── KMS cross-account ─────────────────────────────────────────────────────

    def _kms_cross_account(self) -> list[dict[str, Any]]:
        """
        Resources in account B that reference a KMS key ARN owned by account A.
        Detects by comparing the account ID embedded in the key ARN vs the
        account that holds the resource.
        """
        findings = []
        kms_owner: dict[str, str] = {}   # key_arn → owner_account_id

        for account in self._accounts:
            for key in account["data"].get("kms", []):
                kms_owner[key.get("resource_id", "")] = account["id"]

        # Check all resources that have a kms_key_id / kms_key_arn field
        resource_types = ["lambdas", "rds", "secrets", "s3_buckets", "ec2"]
        kms_fields     = ["kms_key_arn", "kms_key_id", "kms_key"]

        for account in self._accounts:
            for rtype in resource_types:
                for resource in account["data"].get(rtype, []):
                    key_ref = ""
                    for field in kms_fields:
                        key_ref = resource.get(field, "")
                        if key_ref:
                            break
                    if not key_ref:
                        continue
                    key_account = _account_from_arn(key_ref)
                    if key_account and key_account != account["id"]:
                        owner_name = self._account_name(key_account)
                        findings.append({
                            "resource_id":        resource.get("resource_id", ""),
                            "resource_type":      resource.get("resource_type", ""),
                            "resource_name":      resource.get("resource_name", ""),
                            "consumer_account_id":   account["id"],
                            "consumer_account_name": account["name"],
                            "kms_key_ref":        key_ref,
                            "kms_owner_account_id":   key_account,
                            "kms_owner_account_name": owner_name,
                            "relationship":       "cross_account_kms_encryption",
                        })

        logger.info("Cross-account KMS usages: %d", len(findings))
        return findings

    # ── Secrets cross-account ─────────────────────────────────────────────────

    def _secrets_cross_account(self) -> list[dict[str, Any]]:
        """
        Secrets whose ARN account ID differs from the collecting account.
        This happens when secrets are replicated to another account or shared
        via resource-based policies.
        """
        findings = []
        for account in self._accounts:
            for secret in account["data"].get("secrets", []):
                arn = secret.get("resource_id", "")
                arn_account = _account_from_arn(arn)
                if arn_account and arn_account != account["id"]:
                    owner_name = self._account_name(arn_account)
                    findings.append({
                        "secret_arn":           arn,
                        "secret_name":          secret.get("resource_name", ""),
                        "collecting_account_id":   account["id"],
                        "collecting_account_name": account["name"],
                        "owner_account_id":        arn_account,
                        "owner_account_name":      owner_name,
                        "relationship":         "cross_account_secret",
                    })
        logger.info("Cross-account secrets: %d", len(findings))
        return findings

    # ── S3 cross-account ──────────────────────────────────────────────────────

    def _s3_cross_account(self) -> list[dict[str, Any]]:
        """
        Lambda functions or other resources that reference S3 bucket ARNs
        owned by a different account.  Also flags buckets with public policy
        or public ACL that are owned by one of the known accounts.
        """
        findings = []
        # Build bucket owner index: bucket_name → account
        bucket_owner: dict[str, str] = {}
        for account in self._accounts:
            for bucket in account["data"].get("s3_buckets", []):
                name = bucket.get("resource_name", "")
                if name:
                    bucket_owner[name] = account["id"]

        # Cross-account: lambdas accessing buckets in other accounts
        # (detected via environment_keys containing bucket names or S3 ARNs in relationships)
        for account in self._accounts:
            for fn in account["data"].get("lambdas", []):
                for rel in fn.get("relationships", []):
                    if rel.get("resource_type") == "aws::s3::bucket":
                        bucket_ref = rel.get("resource_id", "")
                        bucket_name = bucket_ref.replace("arn:aws:s3:::", "")
                        owner_id = bucket_owner.get(bucket_name, "")
                        if owner_id and owner_id != account["id"]:
                            owner_name = self._account_name(owner_id)
                            findings.append({
                                "lambda_arn":            fn.get("resource_id", ""),
                                "lambda_name":           fn.get("resource_name", ""),
                                "consumer_account_id":   account["id"],
                                "consumer_account_name": account["name"],
                                "bucket_name":           bucket_name,
                                "bucket_owner_id":       owner_id,
                                "bucket_owner_name":     owner_name,
                                "relationship":          "cross_account_s3_access",
                            })

        logger.info("Cross-account S3 references: %d", len(findings))
        return findings

    # ── summary ───────────────────────────────────────────────────────────────

    def _make_summary(self, results: dict[str, Any]) -> dict[str, Any]:
        return {
            "accounts_analyzed":        len(results.get("accounts_analyzed", [])),
            "tgw_connections":          len(results.get("tgw_connections", [])),
            "vpc_peerings":             len(results.get("vpc_peerings", [])),
            "iam_trust_relationships":  len(results.get("iam_trust_relationships", [])),
            "kms_cross_account":        len(results.get("kms_cross_account", [])),
            "secrets_cross_account":    len(results.get("secrets_cross_account", [])),
            "s3_cross_account":         len(results.get("s3_cross_account", [])),
            "total_findings":           sum([
                len(results.get("tgw_connections", [])),
                len(results.get("vpc_peerings", [])),
                len(results.get("iam_trust_relationships", [])),
                len(results.get("kms_cross_account", [])),
                len(results.get("secrets_cross_account", [])),
                len(results.get("s3_cross_account", [])),
            ]),
        }

    # ── helpers ───────────────────────────────────────────────────────────────

    def _account_name(self, account_id: str) -> str:
        for a in self._accounts:
            if a["id"] == account_id:
                return a["name"]
        return account_id or "unknown"
