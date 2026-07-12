from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import boto3

from config import AccountConfig, AppConfig
from utils.aws_clients import (
    get_ec2_client, get_elbv2_client, get_eks_client,
    get_lambda_client, get_rds_client, get_iam_client,
    get_kms_client, get_secretsmanager_client, get_s3_client,
    get_ce_client, get_backup_client, get_session, resolve_identity, resolve_account_name,
    get_logs_client, get_dynamodb_client, get_apigateway_client, get_apigatewayv2_client,
    get_sqs_client, get_sns_client, get_events_client, get_stepfunctions_client,
    get_cloudtrail_client, get_config_client, get_guardduty_client, get_acm_client,
    get_wafv2_client, get_ecr_client, get_route53_client,
)
from utils.writer import OutputWriter

from collectors.vpcs import VPCCollector
from collectors.subnets import SubnetCollector
from collectors.route_tables import RouteTableCollector
from collectors.internet_gateways import InternetGatewayCollector
from collectors.nat_gateways import NatGatewayCollector
from collectors.transit_gateways import TransitGatewayCollector
from collectors.transit_gateway_attachments import TransitGatewayAttachmentCollector
from collectors.security_groups import SecurityGroupCollector
from collectors.nacls import NACLCollector
from collectors.vpc_peerings import VPCPeeringCollector
from collectors.network_interfaces import NetworkInterfaceCollector
from collectors.vpc_endpoints import VPCEndpointCollector
from collectors.ec2 import EC2Collector
from collectors.ebs import EBSCollector
from collectors.snapshots import SnapshotCollector
from collectors.amis import AMICollector
from collectors.aws_backup import AWSBackupCollector
from collectors.cloudwatch_logs import CloudWatchLogsCollector
from collectors.elastic_ips import ElasticIPCollector
from collectors.dynamodb import DynamoDBCollector
from collectors.api_gateway import APIGatewayCollector
from collectors.sqs import SQSCollector
from collectors.sns import SNSCollector
from collectors.eventbridge import EventBridgeCollector
from collectors.step_functions import StepFunctionsCollector
from collectors.cloudtrail import CloudTrailCollector
from collectors.config_service import ConfigServiceCollector
from collectors.guardduty import GuardDutyCollector
from collectors.acm import ACMCollector
from collectors.waf import WAFCollector
from collectors.ecr import ECRCollector
from collectors.route53 import Route53Collector
from collectors.iam_users import IAMUsersCollector
from collectors.iam_groups import IAMGroupsCollector
from collectors.load_balancers import LoadBalancerCollector
from collectors.target_groups import TargetGroupCollector
from collectors.eks import EKSCollector
from collectors.kubernetes_workloads import KubernetesWorkloadsCollector
from collectors.lambdas import LambdaCollector
from collectors.rds import RDSCollector
from collectors.iam_roles import IAMRolesCollector
from collectors.kms import KMSCollector
from collectors.secrets_manager import SecretsManagerCollector
from collectors.s3 import S3Collector
from collectors.costs import CostCollector

from topology.subnet_classifier import SubnetClassifier
from topology.dependency_mapper import DependencyMapper
from topology.network_graph import NetworkGraph
from topology.relationship_engine import RelationshipEngine
from topology.security_analyzer import SecurityAnalyzer, critical_findings, public_exposure_summary
from topology.cross_account_mapper import CrossAccountMapper

logger = logging.getLogger(__name__)


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )


def collect_region(
    account: AccountConfig,
    region: str,
    writer: OutputWriter,
    session: boto3.Session | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Run all collectors for one account × region pair. Returns collected data by resource type."""
    if session is None:
        session = get_session(account)
    ec2 = get_ec2_client(session, region)
    elbv2 = get_elbv2_client(session, region)
    eks = get_eks_client(session, region)

    ctx = {
        "account_id": account.account_id,
        "account_name": account.account_name,
        "region": region,
    }

    # Ordered so topology-dependent collectors run after their dependencies
    network_collectors: list[tuple[str, Any]] = [
        ("vpcs", VPCCollector(ec2, **ctx)),
        ("subnets", SubnetCollector(ec2, **ctx)),
        ("route_tables", RouteTableCollector(ec2, **ctx)),
        ("internet_gateways", InternetGatewayCollector(ec2, **ctx)),
        ("nat_gateways", NatGatewayCollector(ec2, **ctx)),
        ("transit_gateways", TransitGatewayCollector(ec2, **ctx)),
        ("transit_gateway_attachments", TransitGatewayAttachmentCollector(ec2, **ctx)),
        ("security_groups", SecurityGroupCollector(ec2, **ctx)),
        ("nacls", NACLCollector(ec2, **ctx)),
        ("vpc_peerings", VPCPeeringCollector(ec2, **ctx)),
        ("network_interfaces", NetworkInterfaceCollector(ec2, **ctx)),
        ("vpc_endpoints", VPCEndpointCollector(ec2, **ctx)),
    ]
    lmb    = get_lambda_client(session, region)
    rds    = get_rds_client(session, region)
    kms    = get_kms_client(session, region)
    sm     = get_secretsmanager_client(session, region)
    backup = get_backup_client(session, region)
    logs_c = get_logs_client(session, region)
    ddb    = get_dynamodb_client(session, region)
    apigw  = get_apigateway_client(session, region)
    apigwv2 = get_apigatewayv2_client(session, region)
    sqs_c  = get_sqs_client(session, region)
    sns_c  = get_sns_client(session, region)
    events = get_events_client(session, region)
    sfn    = get_stepfunctions_client(session, region)
    ct     = get_cloudtrail_client(session, region)
    cfg_c  = get_config_client(session, region)
    gd     = get_guardduty_client(session, region)
    acm_c  = get_acm_client(session, region)
    waf_c  = get_wafv2_client(session, region)
    ecr_c  = get_ecr_client(session, region)

    compute_collectors: list[tuple[str, Any]] = [
        ("ec2",             EC2Collector(ec2, **ctx)),
        ("ebs",             EBSCollector(ec2, **ctx)),
        ("snapshots",       SnapshotCollector(ec2, **ctx)),
        ("amis",            AMICollector(ec2, **ctx)),
        ("elastic_ips",     ElasticIPCollector(ec2, **ctx)),
        ("aws_backup",      AWSBackupCollector(backup, **ctx)),
        ("load_balancers",  LoadBalancerCollector(elbv2, **ctx)),
        ("target_groups",   TargetGroupCollector(elbv2, **ctx)),
        ("eks",             EKSCollector(eks, **ctx)),
        ("lambdas",         LambdaCollector(lmb, **ctx)),
        ("rds",             RDSCollector(rds, **ctx)),
        ("kms",             KMSCollector(kms, **ctx)),
        ("secrets",         SecretsManagerCollector(sm, **ctx)),
        ("cloudwatch_logs", CloudWatchLogsCollector(logs_c, **ctx)),
        ("dynamodb",        DynamoDBCollector(ddb, **ctx)),
        ("api_gateway",     APIGatewayCollector(apigw, apigwv2, **ctx)),
        ("sqs",             SQSCollector(sqs_c, **ctx)),
        ("sns",             SNSCollector(sns_c, **ctx)),
        ("eventbridge",     EventBridgeCollector(events, **ctx)),
        ("step_functions",  StepFunctionsCollector(sfn, **ctx)),
        ("cloudtrail",      CloudTrailCollector(ct, **ctx)),
        ("aws_config",      ConfigServiceCollector(cfg_c, **ctx)),
        ("guardduty",       GuardDutyCollector(gd, **ctx)),
        ("acm",             ACMCollector(acm_c, **ctx)),
        ("waf",             WAFCollector(waf_c, **ctx)),
        ("ecr",             ECRCollector(ecr_c, **ctx)),
    ]

    collected: dict[str, list[dict[str, Any]]] = {}

    for resource_type, collector in network_collectors + compute_collectors:
        data = collector.collect()
        collected[resource_type] = data
        writer.write(account.account_name, resource_type, data)

    # ── Snapshot / AMI cross-enrichment ──────────────────────────────────────
    #    Run AFTER ebs + snapshots + amis are collected in the loop above
    _enrich_snapshots(collected, account, writer)

    # ── Kubernetes workloads (read-only describe) ─────────────────────────────
    k8s_resources: list[dict] = []
    for cluster in collected.get("eks", []):
        if cluster.get("resource_type") != "aws::eks::cluster":
            continue
        if cluster.get("status") != "ACTIVE":
            continue
        try:
            k8s_col = KubernetesWorkloadsCollector(
                cluster=cluster,
                session=session,
                account_id=account.account_id,
                account_name=account.account_name,
                region=region,
            )
            k8s_resources.extend(k8s_col.collect())
        except Exception as exc:
            logger.error(
                "  k8s workloads for cluster %s failed: %s",
                cluster.get("cluster_name"), exc,
            )
    if k8s_resources:
        collected["kubernetes_workloads"] = k8s_resources
        writer.write(account.account_name, "kubernetes_workloads", k8s_resources)

    # ── Topology enrichment ───────────────────────────────────────────────────
    subnets_enriched = SubnetClassifier().classify_all(
        collected.get("subnets", []),
        collected.get("route_tables", []),
    )
    collected["subnets"] = subnets_enriched
    writer.write(account.account_name, "subnets", subnets_enriched)

    chains = DependencyMapper().build_ec2_chains(
        collected.get("ec2", []),
        subnets_enriched,
        collected.get("route_tables", []),
    )
    writer.write(account.account_name, "ec2_topology_chains", chains)

    all_resources = [r for resources in collected.values() for r in resources]

    # ── Capa 2: Relationship Engine ───────────────────────────────────────────
    rel_engine = RelationshipEngine()
    edges = rel_engine.build_all(collected)
    writer.write(account.account_name, "relationships/all_relationships",
                 [e.to_dict() for e in edges])

    # ── Capa 2: Security Analysis ─────────────────────────────────────────────
    sg_analyzer = SecurityAnalyzer()
    sg_analysis = sg_analyzer.analyze_all(collected.get("security_groups", []), all_resources)
    writer.write(account.account_name, "relationships/security_groups_analysis", sg_analysis)
    writer.write(account.account_name, "relationships/security_critical_findings",
                 critical_findings(sg_analysis))
    writer.write(account.account_name, "relationships/security_summary",
                 [public_exposure_summary(sg_analysis)])

    # ── Capa 3: Network Graph (networkx) ──────────────────────────────────────
    graph = NetworkGraph()
    graph.build_from_inventory(all_resources)
    graph.build_from_edges(edges)
    writer.write(account.account_name, "topology/network_graph", [graph.to_dict()])
    writer.write(account.account_name, "topology/graph_summary", [graph.summary()])

    return collected


def _enrich_snapshots(
    collected: dict[str, list[dict[str, Any]]],
    account: Any,
    writer: "OutputWriter",
) -> None:
    """
    Cross-enrich snapshots and AMIs after both are collected:

      snapshot.volume_exists      — True if ebs.json has the source volume
      snapshot.volume_name        — Name tag of the source volume
      snapshot.attached_ec2_name  — EC2 name if the volume is attached
      snapshot.ami_ids            — list of AMI IDs that reference this snapshot
      ami.snapshot_ids            — already set by AMICollector; no change needed
    """
    snapshots = collected.get("snapshots", [])
    amis      = collected.get("amis", [])
    ebs_vols  = collected.get("ebs", [])
    ec2_insts = collected.get("ec2", [])

    if not snapshots:
        return

    # Build lookup: volume_id -> ebs record
    ebs_by_id: dict[str, dict] = {v["resource_id"]: v for v in ebs_vols}

    # Build lookup: instance_id -> ec2 name
    ec2_name_by_id: dict[str, str] = {}
    for inst in ec2_insts:
        iid   = inst.get("resource_id", "")
        iname = inst.get("tags", {}).get("Name") or inst.get("resource_name", "") or iid
        if iid:
            ec2_name_by_id[iid] = iname

    # Build lookup: snapshot_id -> list of AMI IDs that use it
    snap_to_amis: dict[str, list[str]] = {}
    for ami in amis:
        for snap_id in ami.get("snapshot_ids", []):
            snap_to_amis.setdefault(snap_id, []).append(ami["resource_id"])

    # Enrich each snapshot
    for snap in snapshots:
        snap_id = snap["resource_id"]
        vol_id  = snap.get("volume_id", "")

        if vol_id:
            vol = ebs_by_id.get(vol_id)
            snap["volume_exists"] = vol is not None
            if vol:
                snap["volume_name"] = vol.get("resource_name", "") or vol.get("tags", {}).get("Name", "")
                inst_id = vol.get("attached_instance_id", "")
                snap["attached_ec2_name"] = ec2_name_by_id.get(inst_id, "")
        else:
            snap["volume_exists"] = False  # vol_id blank = snapshot of deleted volume

        snap["ami_ids"] = snap_to_amis.get(snap_id, [])

    # Persist enriched snapshots
    if snapshots:
        writer.write(account.account_name, "snapshots", snapshots)
    logger.info(
        "[%s] Snapshot enrichment: %d snapshots, %d AMIs, %d EBS vols",
        account.account_name, len(snapshots), len(amis), len(ebs_vols),
    )


def run(config: AppConfig) -> None:
    writer = OutputWriter(config.output_dir)
    summary: list[dict[str, Any]] = []

    for account in config.accounts:
        session = get_session(account)

        if not account.is_identity_resolved:
            account_id, arn = resolve_identity(session)
            account.account_id = account_id
            if not account.account_name:
                account.account_name = resolve_account_name(session, account_id)
            logger.info("Resolved identity: %s -> account %s (%s)", arn, account_id, account.account_name)

        logger.info(
            "━━ Account: %s (%s) ━━", account.account_name, account.account_id
        )
        account_totals: dict[str, int] = {}

        # ── Global collectors (run once per account, not per region) ─────────
        iam_client = get_iam_client(session)
        iam_data = IAMRolesCollector(iam_client, account.account_id, account.account_name).collect()
        if iam_data:
            writer.write(account.account_name, "iam_roles", iam_data)
            account_totals["iam_roles"] = len(iam_data)

        iam_users_data = IAMUsersCollector(iam_client, account.account_id, account.account_name).collect()
        if iam_users_data:
            writer.write(account.account_name, "iam_users", iam_users_data)
            account_totals["iam_users"] = len(iam_users_data)

        iam_groups_data = IAMGroupsCollector(iam_client, account.account_id, account.account_name).collect()
        if iam_groups_data:
            writer.write(account.account_name, "iam_groups", iam_groups_data)
            account_totals["iam_groups"] = len(iam_groups_data)

        s3_client = get_s3_client(session)
        s3_data = S3Collector(s3_client, session, account.account_id, account.account_name).collect()
        if s3_data:
            writer.write(account.account_name, "s3_buckets", s3_data)
            account_totals["s3_buckets"] = len(s3_data)

        route53_client = get_route53_client(session)
        route53_data = Route53Collector(route53_client, account.account_id, account.account_name).collect()
        if route53_data:
            writer.write(account.account_name, "route53", route53_data)
            account_totals["route53"] = len(route53_data)

        # ── Cost Explorer (global, once per account) ──────────────────────────
        # The only collector that charges per API call (~$0.01/request).
        # Skip with --skip-costs / SKIP_COSTS=1 / config.json "skip_costs": true
        if config.skip_costs:
            logger.info("[%s] Skipping Cost Explorer (--skip-costs)", account.account_name)
        else:
            try:
                from utils.cost_history import merge_and_save
                from pathlib import Path as _Path

                ce_client  = get_ce_client(session)
                cost_data  = CostCollector(ce_client, account.account_id, account.account_name).collect()
                account_dir = _Path(config.output_dir) / account.account_name

                for key, records in cost_data.items():
                    if records:
                        writer.write(account.account_name, key, records)
                        account_totals[key] = len(records)

                # Accumulate history — never loses data older than 90-day window
                history_keys = [
                    ("costs_daily",        "costs_history.json"),
                    ("costs_by_name",      "costs_history_by_name.json"),
                    ("costs_by_apid",      "costs_history_by_apid.json"),
                    ("costs_by_assetid",   "costs_history_by_assetid.json"),
                    ("costs_by_env",       "costs_history_by_env.json"),
                    ("costs_by_usage",     "costs_history_by_usage.json"),
                    ("costs_monthly",      "costs_history_monthly.json"),
                ]
                for data_key, hist_file in history_keys:
                    records = cost_data.get(data_key, [])
                    if records:
                        merge_and_save(records, account_dir / hist_file)

            except Exception as exc:
                logger.warning("Cost Explorer collection failed for %s: %s",
                               account.account_name, exc)

        for region in account.regions:
            logger.info("  Region: %s", region)
            try:
                collected = collect_region(account, region, writer, session=session)
                for resource_type, data in collected.items():
                    account_totals[resource_type] = (
                        account_totals.get(resource_type, 0) + len(data)
                    )
            except Exception as exc:
                logger.error(
                    "Fatal error in account %s / region %s: %s",
                    account.account_name,
                    region,
                    exc,
                    exc_info=True,
                )

        summary.append(
            {
                "account_name": account.account_name,
                "account_id": account.account_id,
                "totals": account_totals,
                "total_resources": sum(account_totals.values()),
            }
        )

    _print_summary(summary)

    # ── Cross-account analysis (runs after ALL accounts are collected) ────────
    if len(config.accounts) > 1:
        logger.info("Running cross-account relationship analysis…")
        try:
            output_path = Path(config.output_dir)
            cross = CrossAccountMapper(output_path)
            results = cross.build_all()
            if results:
                cross_dir = output_path / "cross_account"
                cross_dir.mkdir(parents=True, exist_ok=True)
                for key, data in results.items():
                    out_file = cross_dir / f"{key}.json"
                    with open(out_file, "w", encoding="utf-8") as f:
                        json.dump(data if isinstance(data, list) else [data], f, indent=2, default=str)
                _print_cross_account_summary(results.get("summary", {}))
        except Exception as exc:
            logger.error("Cross-account analysis failed: %s", exc, exc_info=True)


def _print_summary(summary: list[dict[str, Any]]) -> None:
    print("\n" + "═" * 60)
    print("  JERICHO EXTRACTOR — SUMMARY")
    print("═" * 60)
    grand_total = 0
    for entry in summary:
        print(f"\n  Account : {entry['account_name']} ({entry['account_id']})")
        print(f"  Total   : {entry['total_resources']} resources")
        for resource_type, count in sorted(entry["totals"].items()):
            print(f"    {resource_type:<35} {count:>6}")
        grand_total += entry["total_resources"]
    print(f"\n  Grand total: {grand_total} resources across {len(summary)} account(s)")
    print("═" * 60 + "\n")


def _print_cross_account_summary(summary: dict) -> None:
    print("\n" + "═" * 60)
    print("  CROSS-ACCOUNT RELATIONSHIPS")
    print("═" * 60)
    print(f"  Accounts analyzed      : {summary.get('accounts_analyzed', 0)}")
    print(f"  TGW connections        : {summary.get('tgw_connections', 0)}")
    print(f"  VPC peerings           : {summary.get('vpc_peerings', 0)}")
    print(f"  IAM trust              : {summary.get('iam_trust_relationships', 0)}")
    print(f"  KMS cross-account      : {summary.get('kms_cross_account', 0)}")
    print(f"  Secrets cross-account  : {summary.get('secrets_cross_account', 0)}")
    print(f"  S3 cross-account       : {summary.get('s3_cross_account', 0)}")
    print(f"  Total findings         : {summary.get('total_findings', 0)}")
    print("═" * 60 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Jericho Extractor — AWS inventory and topology tool"
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        help="Path to JSON config file (default: load from environment variables)",
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        default=None,
        help="Override output directory",
    )
    parser.add_argument(
        "--skip-costs",
        action="store_true",
        help="Skip Cost Explorer collection — the only collector that charges "
             "per API call (~$0.01/request). Useful for test/dry runs.",
    )
    args = parser.parse_args()

    if args.config:
        config = AppConfig.from_file(args.config)
    else:
        config = AppConfig.from_env()

    if args.output_dir:
        config.output_dir = args.output_dir
    if args.skip_costs:
        config.skip_costs = True

    setup_logging(config.log_level)
    run(config)


if __name__ == "__main__":
    main()
