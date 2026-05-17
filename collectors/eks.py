from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE_CLUSTER   = "aws::eks::cluster"
RESOURCE_TYPE_NODEGROUP = "aws::eks::nodegroup"


class EKSCollector:
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
        logger.info("[%s][%s] Collecting EKS Clusters", self.account_name, self.region)
        results: list[dict[str, Any]] = []
        try:
            cluster_names = self._list_clusters()
            for name in cluster_names:
                cluster = self._get_cluster(name)
                if cluster:
                    results.append(cluster)
                    results.extend(self._collect_nodegroups(name, cluster["resource_id"]))
        except Exception as exc:
            logger.error("[%s][%s] EKS failed: %s", self.account_name, self.region, exc)
        return results

    def _list_clusters(self) -> list[str]:
        names: list[str] = []
        kwargs: dict[str, Any] = {}
        while True:
            resp = self.client.list_clusters(**kwargs)
            names.extend(resp.get("clusters", []))
            next_token = resp.get("nextToken")
            if not next_token:
                break
            kwargs["nextToken"] = next_token
        return names

    def _get_cluster(self, name: str) -> dict[str, Any] | None:
        try:
            resp = self.client.describe_cluster(name=name)
            return self._normalize_cluster(resp["cluster"])
        except Exception as exc:
            logger.warning("[%s][%s] describe_cluster(%s) failed: %s", self.account_name, self.region, name, exc)
            return None

    def _normalize_cluster(self, cluster: dict[str, Any]) -> dict[str, Any]:
        cluster_arn = cluster["arn"]
        vpc_config  = cluster.get("resourcesVpcConfig", {})
        vpc_id      = vpc_config.get("vpcId", "")
        subnet_ids  = vpc_config.get("subnetIds", [])
        sg_ids      = vpc_config.get("securityGroupIds", [])

        relationships = []
        if vpc_id:
            relationships.append(build_relationship("aws::ec2::vpc", vpc_id, "deployed_in_vpc"))
        for sid in subnet_ids:
            relationships.append(build_relationship("aws::ec2::subnet", sid, "uses_subnet"))
        for sg in sg_ids:
            relationships.append(build_relationship("aws::ec2::security_group", sg, "protected_by_sg"))

        return {
            "resource_type":    RESOURCE_TYPE_CLUSTER,
            "resource_id":      cluster_arn,
            "resource_name":    cluster.get("name", ""),
            "account_id":       self.account_id,
            "account_name":     self.account_name,
            "region":           self.region,
            "cluster_name":     cluster.get("name", ""),
            "status":           cluster.get("status", ""),
            "kubernetes_version": cluster.get("version", ""),
            "vpc_id":           vpc_id,
            "subnet_ids":       subnet_ids,
            "security_group_ids": sg_ids,
            "endpoint_public_access":  vpc_config.get("endpointPublicAccess", False),
            "endpoint_private_access": vpc_config.get("endpointPrivateAccess", False),
            "role_arn":         cluster.get("roleArn", ""),
            "logging_enabled":  self._logging_enabled(cluster),
            "tags":             cluster.get("tags", {}),
            "relationships":    relationships,
            "collected_at":     utc_now(),
        }

    def _collect_nodegroups(self, cluster_name: str, cluster_arn: str) -> list[dict[str, Any]]:
        results = []
        try:
            ng_names = self._list_nodegroups(cluster_name)
            for ng_name in ng_names:
                ng = self._get_nodegroup(cluster_name, ng_name, cluster_arn)
                if ng:
                    results.append(ng)
        except Exception as exc:
            logger.warning("[%s][%s] nodegroups for %s failed: %s", self.account_name, self.region, cluster_name, exc)
        return results

    def _list_nodegroups(self, cluster_name: str) -> list[str]:
        names: list[str] = []
        kwargs: dict[str, Any] = {"clusterName": cluster_name}
        while True:
            resp = self.client.list_nodegroups(**kwargs)
            names.extend(resp.get("nodegroups", []))
            next_token = resp.get("nextToken")
            if not next_token:
                break
            kwargs["nextToken"] = next_token
        return names

    def _get_nodegroup(self, cluster_name: str, ng_name: str, cluster_arn: str) -> dict[str, Any] | None:
        try:
            resp = self.client.describe_nodegroup(clusterName=cluster_name, nodegroupName=ng_name)
            return self._normalize_nodegroup(resp["nodegroup"], cluster_arn)
        except Exception as exc:
            logger.warning("[%s][%s] describe_nodegroup(%s/%s) failed: %s", self.account_name, self.region, cluster_name, ng_name, exc)
            return None

    def _normalize_nodegroup(self, ng: dict[str, Any], cluster_arn: str) -> dict[str, Any]:
        ng_arn     = ng["nodegroupArn"]
        subnet_ids = ng.get("subnets", [])
        scaling    = ng.get("scalingConfig", {})

        relationships = [
            build_relationship(RESOURCE_TYPE_CLUSTER, cluster_arn, "belongs_to_cluster")
        ]
        for sid in subnet_ids:
            relationships.append(build_relationship("aws::ec2::subnet", sid, "uses_subnet"))

        return {
            "resource_type":    RESOURCE_TYPE_NODEGROUP,
            "resource_id":      ng_arn,
            "resource_name":    ng.get("nodegroupName", ""),
            "account_id":       self.account_id,
            "account_name":     self.account_name,
            "region":           self.region,
            "cluster_arn":      cluster_arn,
            "nodegroup_name":   ng.get("nodegroupName", ""),
            "status":           ng.get("status", ""),
            "instance_types":   ng.get("instanceTypes", []),
            "ami_type":         ng.get("amiType", ""),
            "capacity_type":    ng.get("capacityType", ""),
            "subnet_ids":       subnet_ids,
            "desired_size":     scaling.get("desiredSize", 0),
            "min_size":         scaling.get("minSize", 0),
            "max_size":         scaling.get("maxSize", 0),
            "disk_size":        ng.get("diskSize", 0),
            "tags":             ng.get("tags", {}),
            "relationships":    relationships,
            "collected_at":     utc_now(),
        }

    @staticmethod
    def _logging_enabled(cluster: dict[str, Any]) -> list[str]:
        enabled = []
        for lc in cluster.get("logging", {}).get("clusterLogging", []):
            if lc.get("enabled"):
                enabled.extend(lc.get("types", []))
        return enabled
