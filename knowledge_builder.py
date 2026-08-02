#!/usr/bin/env python3
"""
Generate Markdown knowledge base from jericho-extractor output.

Reads per-account JSON from output/ and writes structured Markdown documents
to a target directory (e.g. a cloned intelica-aws-knowledge repo).

Usage:
    python knowledge_builder.py --output-dir output --knowledge-dir ../intelica-aws-knowledge
    python knowledge_builder.py --output-dir output --knowledge-dir ../intelica-aws-knowledge --push
    python knowledge_builder.py --output-dir output --knowledge-dir ../intelica-aws-knowledge --account Portal-Prod
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ── loader ────────────────────────────────────────────────────────────────────

def _load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _name(resource: dict, fallback_key: str = "resource_id") -> str:
    return (
        resource.get("tags", {}).get("Name")
        or resource.get("resource_name")
        or resource.get(fallback_key)
        or resource.get("resource_id", "")
    )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _format_rule(rule: dict) -> str:
    """Render a security_groups.py inbound/outbound rule dict as one line."""
    protocol = rule.get("protocol", "")
    proto_label = "ALL" if protocol == "-1" else protocol.upper()

    from_port = rule.get("from_port")
    to_port   = rule.get("to_port")
    if from_port is None and to_port is None:
        port_label = "all ports"
    elif from_port == to_port:
        port_label = f"port {from_port}"
    else:
        port_label = f"ports {from_port}-{to_port}"

    sources = (
        rule.get("ipv4_ranges", [])
        + rule.get("ipv6_ranges", [])
        + [f"sg:{g}" for g in rule.get("referenced_group_ids", [])]
        + [f"pl:{p}" for p in rule.get("prefix_list_ids", [])]
    )
    source_label = ", ".join(sources) if sources else "—"

    return f"{proto_label} {port_label} ← {source_label}"


# ── per-account builder ───────────────────────────────────────────────────────

class AccountKnowledgeBuilder:
    def __init__(self, account_dir: Path, out_dir: Path) -> None:
        self.account_dir = account_dir
        self.out_dir     = out_dir
        self.account     = account_dir.name
        self.out_dir.mkdir(parents=True, exist_ok=True)

        # Load all data up front
        self.vpcs        = _load(account_dir / "vpcs.json")
        self.subnets     = _load(account_dir / "subnets.json")
        self.igws        = _load(account_dir / "internet_gateways.json")
        self.nats        = _load(account_dir / "nat_gateways.json")
        self.tgw_atts    = _load(account_dir / "transit_gateway_attachments.json")
        self.tgws        = _load(account_dir / "transit_gateways.json")
        self.vpc_eps     = _load(account_dir / "vpc_endpoints.json")
        self.vpc_peer    = _load(account_dir / "vpc_peerings.json")
        self.sgs         = _load(account_dir / "security_groups.json")
        self.ec2         = _load(account_dir / "ec2.json")
        self.eks         = _load(account_dir / "eks.json")
        self.lambdas     = _load(account_dir / "lambdas.json")
        self.rds         = _load(account_dir / "rds.json")
        self.s3          = _load(account_dir / "s3_buckets.json")
        self.kms         = _load(account_dir / "kms.json")
        self.secrets     = _load(account_dir / "secrets.json")
        self.iam         = _load(account_dir / "iam_roles.json")
        self.lbs         = _load(account_dir / "load_balancers.json")
        self.k8s         = _load(account_dir / "kubernetes_workloads.json")

        # Derived
        self.account_id  = self._resolve_account_id()
        self.region      = self._resolve_region()
        self.prod_vpc    = self._resolve_prod_vpc()

        # Indexes
        self.sg_by_id: dict[str, dict] = {sg["resource_id"]: sg for sg in self.sgs}
        self.subnet_by_id: dict[str, dict] = {s["resource_id"]: s for s in self.subnets}
        self.kms_by_id: dict[str, dict] = {k["resource_id"]: k for k in self.kms}
        self.kms_by_alias: dict[str, dict] = {}
        for k in self.kms:
            for alias in k.get("aliases", []):
                self.kms_by_alias[alias] = k

    def build_all(self) -> None:
        logger.info("[%s] Generating knowledge base…", self.account)
        self._write("overview.md",        self._overview())
        self._write("networking.md",      self._networking())
        self._write("compute.md",         self._compute())
        self._write("data.md",            self._data())
        self._write("security.md",        self._security())
        self._write("placement_guide.md", self._placement_guide())
        logger.info("[%s] Done — %s", self.account, self.out_dir)

    # ── file writer ───────────────────────────────────────────────────────────

    def _write(self, filename: str, content: str) -> None:
        path = self.out_dir / filename
        path.write_text(content.strip() + "\n", encoding="utf-8")
        logger.info("[%s]  -> %s", self.account, filename)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _resolve_account_id(self) -> str:
        for lst in [self.vpcs, self.ec2, self.lambdas, self.rds]:
            if lst:
                return lst[0].get("account_id", "")
        return ""

    def _resolve_region(self) -> str:
        for lst in [self.vpcs, self.ec2, self.lambdas]:
            if lst:
                return lst[0].get("region", "")
        return ""

    def _resolve_prod_vpc(self) -> dict | None:
        """Return the non-default VPC (production), or first VPC if only one exists."""
        non_default = [v for v in self.vpcs if not v.get("is_default", False)]
        return non_default[0] if non_default else (self.vpcs[0] if self.vpcs else None)

    def _subnet_table(self, subnets: list[dict]) -> str:
        rows = []
        for s in sorted(subnets, key=lambda x: x.get("availability_zone", "")):
            name = _name(s)
            rows.append(
                f"| {name} | `{s['resource_id']}` "
                f"| {s.get('cidr_block','')} "
                f"| {s.get('availability_zone','').split('-')[-1]} "
                f"| {s.get('available_ip_count', '?')} |"
            )
        header = "| Name | ID | CIDR | AZ | Free IPs |\n|---|---|---|---|---|"
        return header + "\n" + "\n".join(rows) if rows else "_None_"

    def _sg_name(self, sg_id: str) -> str:
        sg = self.sg_by_id.get(sg_id, {})
        return sg.get("tags", {}).get("Name") or sg.get("group_name") or sg_id

    def _kms_display(self, key_ref: str) -> str:
        if not key_ref:
            return "_none_"
        k = self.kms_by_id.get(key_ref) or self.kms_by_alias.get(key_ref)
        if k:
            aliases = k.get("aliases", [])
            return aliases[0] if aliases else k.get("key_id", key_ref)
        # key_ref may be an alias directly
        parts = key_ref.split("/")
        return parts[-1] if parts else key_ref

    # ── overview ──────────────────────────────────────────────────────────────

    def _overview(self) -> str:
        eks_clusters  = [e for e in self.eks if e.get("resource_type") == "aws::eks::cluster"]
        eks_ngs       = [e for e in self.eks if e.get("resource_type") == "aws::eks::nodegroup"]
        active_ec2    = [e for e in self.ec2 if e.get("state") != "terminated"]
        customer_kms  = [k for k in self.kms if k.get("key_manager") == "CUSTOMER" and k.get("enabled")]

        lines = [
            f"# {self.account} — Account Overview",
            "",
            f"**Account ID:** {self.account_id}  ",
            f"**Region:** {self.region}  ",
            f"**Last updated:** {_now()}",
            "",
            "## Resource Summary",
            "",
            "| Resource | Count |",
            "|---|---|",
            f"| VPCs | {len(self.vpcs)} |",
            f"| Subnets | {len(self.subnets)} |",
            f"| EC2 Instances (active) | {len(active_ec2)} |",
            f"| EKS Clusters | {len(eks_clusters)} |",
            f"| EKS Node Groups | {len(eks_ngs)} |",
            f"| Lambda Functions | {len(self.lambdas)} |",
            f"| RDS Instances | {len(self.rds)} |",
            f"| Load Balancers | {len(self.lbs)} |",
            f"| S3 Buckets | {len(self.s3)} |",
            f"| KMS Keys (customer) | {len(customer_kms)} |",
            f"| Secrets | {len(self.secrets)} |",
            f"| Security Groups | {len(self.sgs)} |",
            "",
        ]

        if self.prod_vpc:
            vpc_name = _name(self.prod_vpc)
            lines += [
                "## Production VPC",
                "",
                f"**{vpc_name}** (`{self.prod_vpc['resource_id']}`)",
                f"- CIDR: `{self.prod_vpc.get('cidr_block','')}`",
                f"- Region: {self.region}",
                "- Contains all production workloads",
                "",
            ]

        # Key services
        lines += ["## Key Services Running", ""]
        if eks_clusters:
            for c in eks_clusters:
                lines.append(f"- **EKS Cluster:** {c.get('cluster_name', _name(c))} — status: {c.get('status','')}")
        if self.rds:
            for r in self.rds:
                lines.append(f"- **RDS:** {r.get('resource_name','')} ({r.get('engine','')} {r.get('engine_version','')}, {r.get('instance_class','')})")
        if self.lambdas:
            in_vpc = [l for l in self.lambdas if l.get("vpc_id")]
            lines.append(f"- **Lambda:** {len(self.lambdas)} functions ({len(in_vpc)} inside VPC)")
        if self.lbs:
            lines.append(f"- **Load Balancers:** {len(self.lbs)} ({sum(1 for l in self.lbs if l.get('lb_type')=='application')} ALB, {sum(1 for l in self.lbs if l.get('lb_type')=='network')} NLB)")
        if self.s3:
            lines.append(f"- **S3:** {len(self.s3)} buckets")

        return "\n".join(lines)

    # ── networking ────────────────────────────────────────────────────────────

    def _networking(self) -> str:
        lines = [
            f"# {self.account} — Networking",
            "",
            f"_Last updated: {_now()}_",
            "",
        ]

        for vpc in self.vpcs:
            vpc_id   = vpc["resource_id"]
            vpc_name = _name(vpc)
            vpc_subnets = [s for s in self.subnets if s.get("vpc_id") == vpc_id]
            is_default  = vpc.get("is_default", False)

            lines += [
                f"## VPC: {vpc_name}",
                "",
                f"**ID:** `{vpc_id}`  ",
                f"**CIDR:** `{vpc.get('cidr_block','')}`  ",
                f"**Default VPC:** {'Yes — avoid for production workloads' if is_default else 'No (production)'}",
                "",
            ]

            for stype in ["public", "private", "isolated", "unknown"]:
                label = {
                    "public":   "Public Subnets (route to Internet Gateway — for ALBs, NAT GWs)",
                    "private":  "Private Subnets (route through NAT — recommended for Lambda, EC2, EKS nodes)",
                    "isolated": "Isolated Subnets (no internet route — recommended for RDS, restricted workloads)",
                    "unknown":  "Unknown Subnets",
                }[stype]
                subs = [s for s in vpc_subnets if s.get("subnet_type") == stype]
                if subs:
                    lines += [f"### {label}", "", self._subnet_table(subs), ""]

            # IGW
            igws = [igw for igw in self.igws if vpc_id in igw.get("attached_vpc_ids", [])]
            if igws:
                lines += ["### Internet Gateway", ""]
                for igw in igws:
                    lines.append(f"- `{igw['resource_id']}` — provides inbound/outbound internet for public subnets")
                lines.append("")

            # NAT
            vpc_subnet_ids = {s["resource_id"] for s in vpc_subnets}
            nats = [n for n in self.nats if n.get("subnet_id") in vpc_subnet_ids]
            if nats:
                lines += ["### NAT Gateway", ""]
                for nat in nats:
                    sub = self.subnet_by_id.get(nat.get("subnet_id",""), {})
                    sub_name = _name(sub) or nat.get("subnet_id","")
                    lines.append(
                        f"- `{nat['resource_id']}` in **{sub_name}** ({nat.get('state','')})"
                    )
                    lines.append("  - Provides outbound internet for private subnets")
                    lines.append("  - Cost: ~$0.045/hour + $0.045/GB processed (eu-south-2)")
                lines.append("")

            # VPC Endpoints
            vpc_eps = [ep for ep in self.vpc_eps
                       if any(sid in vpc_subnet_ids for sid in ep.get("associated_subnet_ids", []))
                       or ep.get("vpc_id") == vpc_id]
            if vpc_eps:
                lines += ["### VPC Endpoints (avoid NAT costs for AWS services)", ""]
                for ep in vpc_eps:
                    svc = ep.get("service_name", "").split(".")[-1]
                    ep_type = ep.get("vpc_endpoint_type", "")
                    cost = "free" if ep_type == "Gateway" else "~$0.01/hour per AZ"
                    lines.append(f"- **{svc}** ({ep_type}) — {cost}")
                lines.append("")

            # TGW
            tgw_atts = [a for a in self.tgw_atts if a.get("resource_id_ref") == vpc_id]
            if tgw_atts:
                lines += ["### Transit Gateway Attachments (cross-account connectivity)", ""]
                for att in tgw_atts:
                    lines.append(
                        f"- Attachment `{att['resource_id']}` → TGW `{att.get('transit_gateway_id','')}`"
                    )
                    lines.append("  - Enables routing to other accounts (Interchange, Network, Analytics)")
                lines.append("")

            # VPC Peering
            peerings = [p for p in self.vpc_peer
                        if p.get("requester_vpc_info",{}).get("VpcId") == vpc_id
                        or p.get("accepter_vpc_info",{}).get("VpcId") == vpc_id]
            if peerings:
                lines += ["### VPC Peering Connections", ""]
                for p in peerings:
                    req = p.get("requester_vpc_info",{})
                    acc = p.get("accepter_vpc_info",{})
                    lines.append(
                        f"- `{p['resource_id']}` — "
                        f"{req.get('VpcId','')} ({req.get('CidrBlock','')}) ↔ "
                        f"{acc.get('VpcId','')} ({acc.get('CidrBlock','')}) — {p.get('status','')}"
                    )
                lines.append("")

        return "\n".join(lines)

    # ── compute ───────────────────────────────────────────────────────────────

    def _compute(self) -> str:
        lines = [
            f"# {self.account} — Compute",
            "",
            f"_Last updated: {_now()}_",
            "",
        ]

        # EKS
        eks_clusters = [e for e in self.eks if e.get("resource_type") == "aws::eks::cluster"]
        eks_ngs      = [e for e in self.eks if e.get("resource_type") == "aws::eks::nodegroup"]
        if eks_clusters:
            lines += ["## EKS Clusters", ""]
            for c in eks_clusters:
                ns_list    = [w for w in self.k8s if w.get("resource_type") == "aws::eks::k8s_namespace" and w.get("cluster_arn") == c["resource_id"]]
                dep_list   = [w for w in self.k8s if w.get("resource_type") == "aws::eks::k8s_deployment" and w.get("cluster_arn") == c["resource_id"]]
                svc_list   = [w for w in self.k8s if w.get("resource_type") == "aws::eks::k8s_service" and w.get("cluster_arn") == c["resource_id"]]
                ngs_for_c  = [ng for ng in eks_ngs if c.get("cluster_name","") in ng.get("resource_id","")]
                lines += [
                    f"### {c.get('cluster_name', _name(c))}",
                    "",
                    f"**ARN:** `{c['resource_id']}`  ",
                    f"**VPC:** `{c.get('vpc_id','')}`  ",
                    f"**Status:** {c.get('status','')}  ",
                    f"**Version:** {c.get('version','')}",
                    "",
                ]
                if ngs_for_c:
                    lines += ["**Node Groups:**", ""]
                    for ng in ngs_for_c:
                        lines.append(
                            f"- `{ng.get('nodegroup_name','')}` — "
                            f"{ng.get('instance_types',[])} — "
                            f"desired:{ng.get('desired_size',0)} min:{ng.get('min_size',0)} max:{ng.get('max_size',0)}"
                        )
                    lines.append("")
                if ns_list:
                    ns_names = [n.get("resource_name","") for n in ns_list if n.get("resource_name") not in ("kube-system","kube-public","kube-node-lease")]
                    lines.append(f"**Namespaces (workloads):** {', '.join(ns_names)}")
                    lines.append(f"**Deployments:** {len(dep_list)} — **Services:** {len(svc_list)}")
                    lines.append("")

        # Lambda
        if self.lambdas:
            lines += ["## Lambda Functions", ""]
            lines += [
                "| Name | Runtime | Memory | Timeout | VPC | SGs |",
                "|---|---|---|---|---|---|",
            ]
            for fn in sorted(self.lambdas, key=lambda x: x.get("resource_name","")):
                vpc_flag = "Yes" if fn.get("vpc_id") else "**No VPC**"
                sg_names = [self._sg_name(sg) for sg in fn.get("security_group_ids",[])]
                lines.append(
                    f"| {fn.get('resource_name','')} "
                    f"| {fn.get('runtime','')} "
                    f"| {fn.get('memory_mb','')}MB "
                    f"| {fn.get('timeout_seconds','')}s "
                    f"| {vpc_flag} "
                    f"| {', '.join(sg_names) or '—'} |"
                )
            lines.append("")

            # VPC details for each Lambda
            lines += ["### Lambda VPC Details", ""]
            for fn in self.lambdas:
                if not fn.get("vpc_id"):
                    continue
                sub_names = [_name(self.subnet_by_id.get(sid,{})) or sid for sid in fn.get("subnet_ids",[])]
                lines += [
                    f"**{fn.get('resource_name','')}**",
                    f"- Runtime: {fn.get('runtime','')} | Memory: {fn.get('memory_mb','')}MB | Timeout: {fn.get('timeout_seconds','')}s",
                    f"- Subnets: {', '.join(sub_names)}",
                    f"- Execution role: `{fn.get('execution_role','').split('/')[-1]}`",
                    f"- KMS: {self._kms_display(fn.get('kms_key_arn',''))}",
                    f"- Environment variable keys: {', '.join(fn.get('environment_keys',[])) or '—'}",
                    "",
                ]

        # EC2
        active_ec2 = [e for e in self.ec2 if e.get("state") != "terminated"]
        if active_ec2:
            lines += ["## EC2 Instances", ""]
            lines += [
                "| Name | Type | State | Subnet | Private IP |",
                "|---|---|---|---|---|",
            ]
            for inst in sorted(active_ec2, key=lambda x: _name(x)):
                sub = self.subnet_by_id.get(inst.get("subnet_id",""), {})
                sub_name = _name(sub) or inst.get("subnet_id","")
                lines.append(
                    f"| {_name(inst)} "
                    f"| {inst.get('instance_type','')} "
                    f"| {inst.get('state','')} "
                    f"| {sub_name} "
                    f"| {inst.get('private_ip','')} |"
                )
            lines.append("")

        # Load Balancers
        if self.lbs:
            lines += ["## Load Balancers", ""]
            for lb in sorted(self.lbs, key=lambda x: x.get("resource_name","")):
                lb_type = lb.get("lb_type","").upper()
                scheme  = lb.get("scheme","")
                lines += [
                    f"### {lb.get('resource_name','')} ({lb_type})",
                    f"- **DNS:** `{lb.get('dns_name','')}`",
                    f"- **Scheme:** {scheme}",
                    f"- **AZs:** {', '.join(az.get('ZoneName','') for az in lb.get('availability_zones',[]))}",
                    "",
                ]

        return "\n".join(lines)

    # ── data ─────────────────────────────────────────────────────────────────

    def _data(self) -> str:
        lines = [
            f"# {self.account} — Data Layer",
            "",
            f"_Last updated: {_now()}_",
            "",
        ]

        # RDS
        if self.rds:
            lines += ["## RDS Databases", ""]
            for db in self.rds:
                sg_names = [self._sg_name(sg) for sg in db.get("security_group_ids", [])]
                lines += [
                    f"### {db.get('resource_name','')}",
                    "",
                    f"**Engine:** {db.get('engine','')} {db.get('engine_version','')}  ",
                    f"**Instance class:** {db.get('instance_class','')}  ",
                    f"**Status:** {db.get('status','')}  ",
                    f"**Endpoint:** `{db.get('endpoint_address','')}:{db.get('endpoint_port','')}` — use this to connect  ",
                    f"**VPC:** `{db.get('vpc_id','')}`  ",
                    f"**Subnet group:** {db.get('subnet_group_name','')}  ",
                    f"**Security Groups:** {', '.join(sg_names) or '—'}  ",
                    f"**Multi-AZ:** {'Yes' if db.get('multi_az') else 'No'}  ",
                    f"**Encrypted:** {'Yes' if db.get('storage_encrypted') else 'No'} — KMS: {self._kms_display(db.get('kms_key_id',''))}  ",
                    f"**Publicly accessible:** {'⚠️ Yes' if db.get('publicly_accessible') else 'No'}  ",
                    f"**Backup retention:** {db.get('backup_retention_days',0)} days  ",
                    f"**Deletion protection:** {'Yes' if db.get('deletion_protection') else 'No'}",
                    "",
                    "> **To connect:** ensure your resource is in a subnet that can reach the security group "
                    f"`{sg_names[0] if sg_names else '—'}` on port {db.get('endpoint_port',5432)}.",
                    "",
                ]

        # S3
        if self.s3:
            public_buckets  = [b for b in self.s3 if b.get("acl_public") or b.get("bucket_policy_public")]
            encrypted       = [b for b in self.s3 if b.get("encryption_type") and b.get("encryption_type") != "None"]
            versioned       = [b for b in self.s3 if b.get("versioning_status") == "Enabled"]

            lines += [
                "## S3 Buckets",
                "",
                f"**Total:** {len(self.s3)} buckets  ",
                f"**Encrypted:** {len(encrypted)}  ",
                f"**Versioning enabled:** {len(versioned)}  ",
                f"**Publicly accessible:** {len(public_buckets)}{'  ⚠️' if public_buckets else ''}",
                "",
                "| Bucket | Region | Encryption | Versioning | Public |",
                "|---|---|---|---|---|",
            ]
            for b in sorted(self.s3, key=lambda x: x.get("resource_name","")):
                pub_flag  = "⚠️ Yes" if (b.get("acl_public") or b.get("bucket_policy_public")) else "No"
                enc       = b.get("encryption_type","None")
                ver       = b.get("versioning_status","Disabled")
                lines.append(
                    f"| {b.get('resource_name','')} "
                    f"| {b.get('region','')} "
                    f"| {enc} "
                    f"| {ver} "
                    f"| {pub_flag} |"
                )
            lines.append("")

        # Secrets
        if self.secrets:
            lines += [
                "## Secrets Manager",
                "",
                f"**Total secrets:** {len(self.secrets)}",
                "",
                "| Secret | KMS Key | Rotation | Last Changed |",
                "|---|---|---|---|",
            ]
            for s in sorted(self.secrets, key=lambda x: x.get("resource_name","")):
                rot = "✅ Yes" if s.get("rotation_enabled") else "No"
                kms = self._kms_display(s.get("kms_key_id",""))
                changed = str(s.get("last_changed_date",""))[:10]
                lines.append(
                    f"| {s.get('resource_name','')} | {kms} | {rot} | {changed} |"
                )
            lines.append("")

        return "\n".join(lines)

    # ── security ──────────────────────────────────────────────────────────────

    def _security(self) -> str:
        lines = [
            f"# {self.account} — Security",
            "",
            f"_Last updated: {_now()}_",
            "",
        ]

        # KMS
        customer_keys = [k for k in self.kms if k.get("key_manager") == "CUSTOMER" and k.get("enabled")]
        if customer_keys:
            lines += ["## KMS Keys (Customer Managed)", ""]
            for k in customer_keys:
                aliases = k.get("aliases", [])
                alias_str = aliases[0] if aliases else k.get("key_id","")
                lines += [
                    f"### {alias_str}",
                    f"- **Key ID:** `{k.get('key_id','')}`  ",
                    f"- **Usage:** {k.get('key_usage','')}  ",
                    f"- **Rotation:** {'Enabled' if k.get('rotation_enabled') else 'Disabled'}  ",
                    f"- **Multi-region:** {'Yes' if k.get('multi_region') else 'No'}  ",
                    f"- **Description:** {k.get('description','—')}",
                    "",
                ]

        # IAM roles by service
        lines += ["## IAM Roles by Trusted Service", ""]
        service_groups: dict[str, list[dict]] = {}
        for role in self.iam:
            for svc in role.get("trusted_services", []):
                service_groups.setdefault(svc, []).append(role)

        priority_services = [
            "lambda.amazonaws.com", "ec2.amazonaws.com", "eks.amazonaws.com",
            "ecs-tasks.amazonaws.com", "rds.amazonaws.com", "scheduler.amazonaws.com",
        ]
        for svc in priority_services:
            roles = service_groups.get(svc, [])
            if not roles:
                continue
            lines += [f"### {svc}", ""]
            for r in roles[:10]:  # cap at 10 per service
                policies = [p["PolicyName"] for p in r.get("attached_policies", [])]
                lines.append(
                    f"- **{r.get('resource_name','')}** — "
                    f"policies: {', '.join(policies[:3]) or '—'}"
                    f"{'...' if len(policies) > 3 else ''}"
                )
            if len(roles) > 10:
                lines.append(f"  _(+ {len(roles)-10} more)_")
            lines.append("")

        # Key security groups
        lines += ["## Security Groups (key ones)", ""]
        named_sgs = [sg for sg in self.sgs if sg.get("tags",{}).get("Name") or sg.get("group_name","").startswith("itl-")]
        for sg in sorted(named_sgs, key=lambda x: _name(x))[:20]:
            sg_name  = _name(sg)
            inbound  = sg.get("inbound_rules", [])
            outbound = sg.get("outbound_rules", [])
            lines.append(f"- **{sg_name}** (`{sg['resource_id']}`) — {len(inbound)} inbound rules, {len(outbound)} outbound rules")
            for rule in inbound[:5]:
                lines.append(f"    - IN  {_format_rule(rule)}")
            if len(inbound) > 5:
                lines.append(f"    - _(+ {len(inbound)-5} more inbound)_")
            for rule in outbound[:5]:
                lines.append(f"    - OUT {_format_rule(rule)}")
            if len(outbound) > 5:
                lines.append(f"    - _(+ {len(outbound)-5} more outbound)_")
        if len(named_sgs) > 20:
            lines.append(f"\n_(+ {len(named_sgs)-20} more security groups)_")
        lines.append("")

        return "\n".join(lines)

    # ── placement guide ───────────────────────────────────────────────────────

    def _placement_guide(self) -> str:
        """The most important document — answers 'what do I need to create X?'"""
        lines = [
            f"# {self.account} — Placement Guide",
            "",
            "_Use this document when creating new resources in this account._  ",
            f"_Last updated: {_now()}_",
            "",
        ]

        if not self.prod_vpc:
            lines.append("_No production VPC found._")
            return "\n".join(lines)

        vpc_id   = self.prod_vpc["resource_id"]
        vpc_name = _name(self.prod_vpc)
        vpc_subnets = [s for s in self.subnets if s.get("vpc_id") == vpc_id]

        private_subs  = [s for s in vpc_subnets if s.get("subnet_type") == "private"]
        public_subs   = [s for s in vpc_subnets if s.get("subnet_type") == "public"]
        isolated_subs = [s for s in vpc_subnets if s.get("subnet_type") == "isolated"]

        # VPC Endpoints
        vpc_ep_services = [ep.get("service_name","").split(".")[-1] for ep in self.vpc_eps]

        # Customer KMS keys
        customer_kms = [k for k in self.kms if k.get("key_manager") == "CUSTOMER" and k.get("enabled")]
        default_kms  = customer_kms[0] if customer_kms else None
        default_kms_display = self._kms_display(default_kms["resource_id"]) if default_kms else "—"

        # Lambda IAM roles
        lambda_roles = [r for r in self.iam if "lambda.amazonaws.com" in r.get("trusted_services", [])]

        # ── Lambda ──
        lines += [
            "## Creating a Lambda Function",
            "",
            f"### Use this VPC: {vpc_name}",
            f"**ID:** `{vpc_id}`  ",
            f"**CIDR:** `{self.prod_vpc.get('cidr_block','')}`",
            "",
            "### Recommended subnets (private, 2 AZs for HA)",
            "",
        ]
        if private_subs:
            lines.append(self._subnet_table(private_subs))
        else:
            lines.append("_No private subnets found — consider using isolated subnets_")
        lines.append("")

        # Existing Lambda SGs
        existing_lambda_sg_ids: set[str] = set()
        for fn in self.lambdas:
            existing_lambda_sg_ids.update(fn.get("security_group_ids", []))
        if existing_lambda_sg_ids:
            lines += ["### Security Groups used by existing Lambdas (reuse or create similar)", ""]
            for sg_id in existing_lambda_sg_ids:
                sg = self.sg_by_id.get(sg_id, {})
                lines.append(f"- `{sg_id}` — {_name(sg)}")
            lines.append("")

        if lambda_roles:
            lines += ["### IAM Execution Roles available for Lambda", ""]
            for r in lambda_roles[:8]:
                policies = [p["PolicyName"] for p in r.get("attached_policies", [])]
                lines.append(
                    f"- **{r.get('resource_name','')}**"
                    + (f" — policies: {', '.join(policies[:3])}" if policies else "")
                )
            lines += ["", "_If none fits, create a new role with trust policy for `lambda.amazonaws.com`_", ""]

        lines += [
            "### KMS encryption",
            f"- Default key: **{default_kms_display}**",
            "",
            "### VPC Endpoints available (avoid NAT Gateway costs)",
        ]
        for svc in vpc_ep_services:
            lines.append(f"- **{svc}** — Lambda can reach this service without going through NAT")
        lines += [
            "",
            "### ⚠️ Important considerations",
            "- Lambdas in private subnets use the NAT Gateway for external internet — cost: ~$0.045/GB",
            "- Use the S3 VPC Endpoint to avoid NAT costs for S3 calls",
            "- Use the Logs VPC Endpoint for CloudWatch Logs",
            "- Each Lambda in a VPC needs at least 1 private IP per concurrent execution",
            "",
            "### Existing Lambdas (reference patterns)",
            "",
            "| Name | Runtime | Memory | Subnets |",
            "|---|---|---|---|",
        ]
        for fn in self.lambdas:
            if not fn.get("vpc_id"):
                continue
            sub_names = [_name(self.subnet_by_id.get(sid, {})) or sid for sid in fn.get("subnet_ids", [])]
            lines.append(
                f"| {fn.get('resource_name','')} "
                f"| {fn.get('runtime','')} "
                f"| {fn.get('memory_mb','')}MB "
                f"| {', '.join(sub_names)} |"
            )
        lines.append("")

        # ── RDS ──
        lines += [
            "---",
            "",
            "## Creating an RDS Instance",
            "",
            "### Recommended subnets (isolated — no internet)",
            "",
        ]
        if isolated_subs:
            lines.append(self._subnet_table(isolated_subs))
        else:
            lines.append("_No isolated subnets found — use private subnets and restrict via SG_")
        lines.append("")

        # Existing RDS SG
        existing_rds_sg_ids: set[str] = set()
        for db in self.rds:
            existing_rds_sg_ids.update(db.get("security_group_ids", []))
        if existing_rds_sg_ids:
            lines += ["### Security Groups used by existing RDS (reuse or create similar)", ""]
            for sg_id in existing_rds_sg_ids:
                sg = self.sg_by_id.get(sg_id, {})
                lines.append(f"- `{sg_id}` — {_name(sg)}")
            lines.append("")

        if self.rds:
            lines += ["### Existing RDS (reference)", ""]
            for db in self.rds:
                lines += [
                    f"**{db.get('resource_name','')}**",
                    f"- Engine: {db.get('engine','')} {db.get('engine_version','')} / Class: {db.get('instance_class','')}",
                    f"- Endpoint: `{db.get('endpoint_address','')}:{db.get('endpoint_port','')}`",
                    f"- KMS: {self._kms_display(db.get('kms_key_id',''))}",
                    "",
                ]

        # ── ECS/container-like context ──
        lines += [
            "---",
            "",
            "## Adding a service to EKS",
            "",
        ]
        eks_clusters = [e for e in self.eks if e.get("resource_type") == "aws::eks::cluster"]
        if eks_clusters:
            for c in eks_clusters:
                c_name = c.get("cluster_name", _name(c))
                ns_list = [w.get("resource_name","") for w in self.k8s
                           if w.get("resource_type") == "aws::eks::k8s_namespace"
                           and w.get("cluster_arn") == c["resource_id"]
                           and w.get("resource_name","") not in ("kube-system","kube-public","kube-node-lease")]
                lines += [
                    f"### Cluster: {c_name}",
                    f"- **VPC:** `{c.get('vpc_id','')}`",
                    f"- **Status:** {c.get('status','')}",
                    f"- **Existing namespaces:** {', '.join(ns_list) or '—'}",
                    "",
                    "**To add a new service:** create a new namespace or deploy into an existing one.  ",
                    "The ALB Ingress Controller creates ALBs automatically from Ingress resources.  ",
                    f"Use tag `elbv2.k8s.aws/cluster: {c_name}` to associate an existing ALB.",
                    "",
                ]
        else:
            lines += ["_No EKS cluster found in this account._", ""]

        # ── S3 ──
        lines += [
            "---",
            "",
            "## Creating an S3 Bucket",
            "",
            "### Recommended configuration based on existing patterns",
            f"- **Region:** {self.region}",
            f"- **Encryption:** SSE-KMS with key **{default_kms_display}**",
            "- **Block all public access:** Yes (all 4 settings enabled)",
            "- **Versioning:** Enabled for critical data",
            "- **Logging:** Enabled pointing to a dedicated logs bucket",
            "",
        ]
        # Naming pattern
        existing_names = [b.get("resource_name","") for b in self.s3 if b.get("resource_name","").startswith("itl-")]
        if existing_names:
            lines += [
                "### Naming convention (based on existing buckets)",
                f"- Pattern: `itl-<assetid>-<account>-<purpose>-<number>`",
                f"- Example: `{existing_names[0]}`",
                "",
            ]

        return "\n".join(lines)


# ── cross-account knowledge ───────────────────────────────────────────────────

class CrossAccountKnowledgeBuilder:
    def __init__(self, output_dir: Path, out_dir: Path) -> None:
        self.output_dir = output_dir
        self.out_dir    = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def build_all(self) -> None:
        cross_dir = self.output_dir / "cross_account"
        if not cross_dir.exists():
            logger.info("No cross_account data found — skipping")
            return

        tgw   = self._load(cross_dir / "tgw_connections.json")
        iam   = self._load(cross_dir / "iam_trust_relationships.json")
        kms   = self._load(cross_dir / "kms_cross_account.json")
        peers = self._load(cross_dir / "vpc_peerings.json")

        self._write("topology_overview.md", self._topology(tgw, peers, iam, kms))
        logger.info("[cross_account]  → topology_overview.md")

    def _load(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]

    def _write(self, filename: str, content: str) -> None:
        (self.out_dir / filename).write_text(content.strip() + "\n", encoding="utf-8")

    def _topology(self, tgw: list, peers: list, iam: list, kms: list) -> str:
        lines = [
            "# Cross-Account Topology Overview",
            "",
            f"_Last updated: {_now()}_",
            "",
            "This document describes how Intelica AWS accounts are connected to each other.",
            "",
        ]

        if tgw:
            lines += ["## Transit Gateway Connections", ""]
            for t in tgw:
                accounts = " ↔ ".join(t.get("accounts", []))
                lines += [
                    f"### TGW: `{t.get('transit_gateway_id','')}`",
                    f"**Connects:** {accounts}",
                    "",
                    "| Account | Attachment ID | VPC |",
                    "|---|---|---|",
                ]
                for att in t.get("attachments", []):
                    lines.append(
                        f"| {att.get('account_name','')} "
                        f"| `{att.get('attachment_id','')}` "
                        f"| `{att.get('vpc_id','')}` |"
                    )
                lines += ["", "_Via Transit Gateway, resources in these accounts can route traffic to each other._", ""]

        if peers:
            lines += ["## VPC Peering Connections", ""]
            for p in peers:
                lines.append(
                    f"- `{p.get('peering_id','')}` — "
                    f"**{p.get('requester_account_name','')}** ({p.get('requester_cidr','')}) ↔ "
                    f"**{p.get('accepter_account_name','')}** ({p.get('accepter_cidr','')}) — {p.get('status','')}"
                )
            lines.append("")

        if iam:
            lines += ["## IAM Cross-Account Trust", ""]
            lines += [
                "| Role | Owner Account | Trusts Account |",
                "|---|---|---|",
            ]
            for r in iam:
                lines.append(
                    f"| {r.get('role_name','')} "
                    f"| {r.get('owner_account_name','')} "
                    f"| {r.get('trusted_account_name','')} |"
                )
            lines.append("")

        if kms:
            lines += ["## KMS Cross-Account Usage", ""]
            lines += [
                "| Resource | Consumer Account | KMS Owner Account |",
                "|---|---|---|",
            ]
            for k in kms:
                lines.append(
                    f"| {k.get('resource_name','')} "
                    f"| {k.get('consumer_account_name','')} "
                    f"| {k.get('kms_owner_account_name','')} |"
                )
            lines.append("")

        if not any([tgw, peers, iam, kms]):
            lines += [
                "No cross-account relationships detected yet.",
                "",
                "_Run the extractor with all 4 accounts configured to populate this document._",
            ]

        return "\n".join(lines)


# ── git push (local clone) ────────────────────────────────────────────────────

def _git_push(knowledge_dir: Path) -> None:
    """Commit and push all changes in a locally cloned knowledge repo."""
    try:
        subprocess.run(["git", "-C", str(knowledge_dir), "add", "."], check=True)
        result = subprocess.run(
            ["git", "-C", str(knowledge_dir), "status", "--porcelain"],
            capture_output=True, text=True,
        )
        if not result.stdout.strip():
            logger.info("Nothing to commit — knowledge base is up to date")
            return
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        subprocess.run(
            ["git", "-C", str(knowledge_dir), "commit", "-m",
             f"chore: update AWS knowledge base — {timestamp}"],
            check=True,
        )
        subprocess.run(["git", "-C", str(knowledge_dir), "push"], check=True)
        logger.info("Knowledge base pushed to GitHub")
    except subprocess.CalledProcessError as exc:
        logger.error("Git push failed: %s", exc)


# ── GitHub API push (no local clone needed) ───────────────────────────────────

import base64
import urllib.request
import urllib.error


class GitHubAPIPusher:
    """
    Push Markdown files directly to a GitHub repo via the REST API.
    No local clone required — only needs a GitHub token.

    Token needs: repo (read + write contents) scope.
    Create at: https://github.com/settings/tokens
    """

    API = "https://api.github.com"

    def __init__(self, token: str, repo: str, branch: str = "main") -> None:
        self.token  = token
        self.repo   = repo          # e.g. "ddvloayza/intelica-aws-knowledge"
        self.branch = branch
        self._sha_cache: dict[str, str] = {}  # path → current SHA (for updates)

    def push_files(self, files: dict[str, str]) -> None:
        """
        Push a dict of {github_path: content} to the repo.
        Creates the file if it doesn't exist, updates it if it does.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        pushed = 0
        for path, content in files.items():
            try:
                self._put_file(path, content, f"chore: update {path} — {timestamp}")
                pushed += 1
            except Exception as exc:
                logger.error("Failed to push %s: %s", path, exc)
        logger.info("GitHub API: pushed %d/%d files to %s", pushed, len(files), self.repo)

    def _put_file(self, path: str, content: str, message: str) -> None:
        url     = f"{self.API}/repos/{self.repo}/contents/{path}"
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        body: dict = {"message": message, "content": encoded, "branch": self.branch}

        # If file already exists we need its SHA to update it
        sha = self._get_sha(path)
        if sha:
            body["sha"] = sha

        data = json.dumps(body).encode("utf-8")
        req  = urllib.request.Request(
            url, data=data, method="PUT",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept":        "application/vnd.github+json",
                "Content-Type":  "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            # Cache new SHA for subsequent runs
            self._sha_cache[path] = result.get("content", {}).get("sha", "")
        logger.debug("Pushed: %s", path)

    def _get_sha(self, path: str) -> str:
        """Return the blob SHA of an existing file, or '' if it doesn't exist."""
        if path in self._sha_cache:
            return self._sha_cache[path]
        url = f"{self.API}/repos/{self.repo}/contents/{path}?ref={self.branch}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept":        "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                sha  = data.get("sha", "")
                self._sha_cache[path] = sha
                return sha
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ""
            raise


# ── in-memory builder ─────────────────────────────────────────────────────────

def _collect_files(output_dir: Path, account_filter: str | None) -> dict[str, str]:
    """
    Generate all Markdown content in memory and return a {github_path: content} dict.
    Used by the GitHub API push mode — no local filesystem write needed.
    """
    import tempfile, shutil

    tmp = Path(tempfile.mkdtemp())
    try:
        for account_dir in sorted(output_dir.iterdir()):
            if not account_dir.is_dir() or account_dir.name == "cross_account":
                continue
            if account_filter and account_dir.name != account_filter:
                continue
            out_dir = tmp / "accounts" / account_dir.name
            AccountKnowledgeBuilder(account_dir, out_dir).build_all()

        if not account_filter:
            out_dir = tmp / "cross_account"
            CrossAccountKnowledgeBuilder(output_dir, out_dir).build_all()

        # Collect all written files
        files: dict[str, str] = {}
        for f in tmp.rglob("*.md"):
            github_path = f.relative_to(tmp).as_posix()
            files[github_path] = f.read_text(encoding="utf-8")
        return files
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Markdown knowledge base from jericho-extractor output"
    )
    parser.add_argument("--output-dir",    default="output",
                        help="jericho-extractor output dir (default: output)")
    parser.add_argument("--knowledge-dir", default=None,
                        help="Path to locally cloned intelica-aws-knowledge repo")
    parser.add_argument("--github-repo",   default=None,
                        help="Push directly via GitHub API, e.g. 'org/intelica-aws-knowledge'")
    parser.add_argument("--github-token",  default=None,
                        help="GitHub personal access token (or set GITHUB_TOKEN env var)")
    parser.add_argument("--github-branch", default="main",
                        help="Target branch for GitHub API push (default: main)")
    parser.add_argument("--account",       default=None,
                        help="Process only this account (default: all)")
    parser.add_argument("--push",          action="store_true",
                        help="Git commit and push (only used with --knowledge-dir)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        print(f"Error: output dir not found: {output_dir}")
        raise SystemExit(1)

    # ── Mode 1: GitHub API (no local clone) ───────────────────────────────────
    if args.github_repo:
        token = args.github_token or __import__("os").environ.get("GITHUB_TOKEN", "")
        if not token:
            print("Error: provide --github-token or set GITHUB_TOKEN env var")
            raise SystemExit(1)

        logger.info("Collecting files in memory…")
        files = _collect_files(output_dir, args.account)
        logger.info("Pushing %d files to GitHub repo: %s", len(files), args.github_repo)
        GitHubAPIPusher(token, args.github_repo, args.github_branch).push_files(files)
        print(f"\nPushed {len(files)} files to https://github.com/{args.github_repo}")
        return

    # ── Mode 2: local clone ───────────────────────────────────────────────────
    if not args.knowledge_dir:
        print("Error: provide --knowledge-dir or --github-repo")
        raise SystemExit(1)

    knowledge_dir = Path(args.knowledge_dir)
    if not knowledge_dir.exists():
        print(f"Error: knowledge dir not found: {knowledge_dir}")
        raise SystemExit(1)

    for account_dir in sorted(output_dir.iterdir()):
        if not account_dir.is_dir() or account_dir.name == "cross_account":
            continue
        if args.account and account_dir.name != args.account:
            continue
        out_dir = knowledge_dir / "accounts" / account_dir.name
        AccountKnowledgeBuilder(account_dir, out_dir).build_all()

    if not args.account:
        out_dir = knowledge_dir / "cross_account"
        CrossAccountKnowledgeBuilder(output_dir, out_dir).build_all()

    if args.push:
        _git_push(knowledge_dir)
    else:
        logger.info("Tip: add --push to commit and push to GitHub automatically")

    print(f"\nKnowledge base written to: {knowledge_dir}")


if __name__ == "__main__":
    main()
