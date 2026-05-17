from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from config import AccountConfig, AppConfig
from utils.aws_clients import get_ec2_client, get_elbv2_client, get_eks_client, get_session, resolve_identity
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
from collectors.load_balancers import LoadBalancerCollector
from collectors.target_groups import TargetGroupCollector
from collectors.eks import EKSCollector
from collectors.kubernetes_workloads import KubernetesWorkloadsCollector

from topology.subnet_classifier import SubnetClassifier
from topology.dependency_mapper import DependencyMapper
from topology.network_graph import NetworkGraph

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
) -> dict[str, list[dict[str, Any]]]:
    """Run all collectors for one account × region pair. Returns collected data by resource type."""
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
    compute_collectors: list[tuple[str, Any]] = [
        ("ec2", EC2Collector(ec2, **ctx)),
        ("load_balancers", LoadBalancerCollector(elbv2, **ctx)),
        ("target_groups", TargetGroupCollector(elbv2, **ctx)),
        ("eks", EKSCollector(eks, **ctx)),
    ]

    collected: dict[str, list[dict[str, Any]]] = {}

    for resource_type, collector in network_collectors + compute_collectors:
        data = collector.collect()
        collected[resource_type] = data
        writer.write(account.account_name, resource_type, data)

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
    graph = NetworkGraph()
    graph.build_from_inventory(all_resources)
    writer.write(account.account_name, "network_graph", [graph.to_dict()])

    return collected


def run(config: AppConfig) -> None:
    writer = OutputWriter(config.output_dir)
    summary: list[dict[str, Any]] = []

    for account in config.accounts:
        if not account.is_identity_resolved:
            session = get_session(account)
            account_id, arn = resolve_identity(session)
            account.account_id = account_id
            if not account.account_name:
                # Use the role/user name from the ARN as a readable label
                account.account_name = account_id
            logger.info("Resolved identity: %s → account %s", arn, account_id)

        logger.info(
            "━━ Account: %s (%s) ━━", account.account_name, account.account_id
        )
        account_totals: dict[str, int] = {}

        for region in account.regions:
            logger.info("  Region: %s", region)
            try:
                collected = collect_region(account, region, writer)
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
    args = parser.parse_args()

    if args.config:
        config = AppConfig.from_file(args.config)
    else:
        config = AppConfig.from_env()

    if args.output_dir:
        config.output_dir = args.output_dir

    setup_logging(config.log_level)
    run(config)


if __name__ == "__main__":
    main()
