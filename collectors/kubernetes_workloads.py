from __future__ import annotations

import base64
import logging
import tempfile
import os
from typing import Any

import boto3
from kubernetes import client as k8s_client

from utils.aws_clients import get_eks_bearer_token
from utils.helpers import utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE_NAMESPACE  = "aws::eks::k8s_namespace"
RESOURCE_TYPE_DEPLOYMENT = "aws::eks::k8s_deployment"
RESOURCE_TYPE_SERVICE    = "aws::eks::k8s_service"
RESOURCE_TYPE_INGRESS    = "aws::eks::k8s_ingress"


class KubernetesWorkloadsCollector:
    """Read-only collector for Kubernetes workloads inside an EKS cluster.

    Only uses list_* and read_* operations — no create/patch/delete/update.
    """

    def __init__(
        self,
        cluster: dict[str, Any],
        session: boto3.Session,
        account_id: str,
        account_name: str,
        region: str,
    ) -> None:
        self.cluster = cluster
        self.session = session
        self.account_id = account_id
        self.account_name = account_name
        self.region = region
        self.cluster_name = cluster.get("cluster_name", "")
        self.cluster_arn = cluster.get("resource_id", "")

    # ── Public entry point ────────────────────────────────────────────────────

    def collect(self) -> list[dict[str, Any]]:
        logger.info(
            "[%s][%s] Collecting Kubernetes workloads for cluster %s",
            self.account_name, self.region, self.cluster_name,
        )
        results: list[dict[str, Any]] = []
        try:
            api = self._build_api_client()
            core_v1   = k8s_client.CoreV1Api(api)
            apps_v1   = k8s_client.AppsV1Api(api)
            net_v1    = k8s_client.NetworkingV1Api(api)

            results.extend(self._collect_namespaces(core_v1))
            results.extend(self._collect_deployments(apps_v1))
            results.extend(self._collect_services(core_v1))
            results.extend(self._collect_ingresses(net_v1))
        except Exception as exc:
            logger.error(
                "[%s][%s] Kubernetes workloads collection failed for %s: %s",
                self.account_name, self.region, self.cluster_name, exc,
            )
        finally:
            try:
                api.rest_client.pool_manager.clear()
            except Exception:
                pass
        return results

    # ── API client bootstrap ──────────────────────────────────────────────────

    def _build_api_client(self) -> k8s_client.ApiClient:
        endpoint = self.cluster.get("endpoint", "")
        ca_data   = self.cluster.get("certificate_authority", "")
        if not endpoint or not ca_data:
            raise ValueError(
                f"Cluster {self.cluster_name} is missing endpoint or certificate_authority. "
                "Re-run the EKS collector first."
            )

        token = get_eks_bearer_token(self.cluster_name, self.session, self.region)

        # Write CA cert to a temp file so the k8s client can verify TLS
        ca_bytes = base64.b64decode(ca_data)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".crt")
        try:
            tmp.write(ca_bytes)
            tmp.flush()
            ca_path = tmp.name
        finally:
            tmp.close()

        configuration = k8s_client.Configuration()
        configuration.host = endpoint
        configuration.verify_ssl = True
        configuration.ssl_ca_cert = ca_path
        configuration.api_key = {"authorization": f"Bearer {token}"}
        configuration.api_key_prefix = {}

        api = k8s_client.ApiClient(configuration)

        # Schedule CA temp file cleanup after client is done
        api._ca_temp_path = ca_path  # type: ignore[attr-defined]
        return api

    # ── Read-only resource collectors ─────────────────────────────────────────

    def _collect_namespaces(self, core_v1: k8s_client.CoreV1Api) -> list[dict[str, Any]]:
        results = []
        try:
            resp = core_v1.list_namespace()
            for ns in resp.items:
                results.append(self._normalize_namespace(ns))
            logger.info(
                "[%s][%s][%s] Collected %d namespaces",
                self.account_name, self.region, self.cluster_name, len(results),
            )
        except Exception as exc:
            logger.warning(
                "[%s][%s][%s] list_namespace failed: %s",
                self.account_name, self.region, self.cluster_name, exc,
            )
        return results

    def _collect_deployments(self, apps_v1: k8s_client.AppsV1Api) -> list[dict[str, Any]]:
        results = []
        try:
            resp = apps_v1.list_deployment_for_all_namespaces()
            for dep in resp.items:
                results.append(self._normalize_deployment(dep))
            logger.info(
                "[%s][%s][%s] Collected %d deployments",
                self.account_name, self.region, self.cluster_name, len(results),
            )
        except Exception as exc:
            logger.warning(
                "[%s][%s][%s] list_deployment_for_all_namespaces failed: %s",
                self.account_name, self.region, self.cluster_name, exc,
            )
        return results

    def _collect_services(self, core_v1: k8s_client.CoreV1Api) -> list[dict[str, Any]]:
        results = []
        try:
            resp = core_v1.list_service_for_all_namespaces()
            for svc in resp.items:
                results.append(self._normalize_service(svc))
            logger.info(
                "[%s][%s][%s] Collected %d services",
                self.account_name, self.region, self.cluster_name, len(results),
            )
        except Exception as exc:
            logger.warning(
                "[%s][%s][%s] list_service_for_all_namespaces failed: %s",
                self.account_name, self.region, self.cluster_name, exc,
            )
        return results

    def _collect_ingresses(self, net_v1: k8s_client.NetworkingV1Api) -> list[dict[str, Any]]:
        results = []
        try:
            resp = net_v1.list_ingress_for_all_namespaces()
            for ing in resp.items:
                results.append(self._normalize_ingress(ing))
            logger.info(
                "[%s][%s][%s] Collected %d ingresses",
                self.account_name, self.region, self.cluster_name, len(results),
            )
        except Exception as exc:
            logger.warning(
                "[%s][%s][%s] list_ingress_for_all_namespaces failed: %s",
                self.account_name, self.region, self.cluster_name, exc,
            )
        return results

    # ── Normalization ──────────────────────────────────────────────────────────

    def _base(self, resource_type: str, uid: str, name: str, namespace: str) -> dict[str, Any]:
        return {
            "resource_type": resource_type,
            "resource_id":   f"{self.cluster_arn}/{resource_type}/{namespace}/{name}" if namespace else f"{self.cluster_arn}/{resource_type}/{name}",
            "resource_name": name,
            "account_id":    self.account_id,
            "account_name":  self.account_name,
            "region":        self.region,
            "cluster_name":  self.cluster_name,
            "cluster_arn":   self.cluster_arn,
            "uid":           uid or "",
            "namespace":     namespace or "",
        }

    def _normalize_namespace(self, ns: Any) -> dict[str, Any]:
        meta = ns.metadata
        record = self._base(RESOURCE_TYPE_NAMESPACE, meta.uid, meta.name, "")
        record.update({
            "status":        ns.status.phase if ns.status else "",
            "labels":        dict(meta.labels or {}),
            "annotations":   _safe_annotations(meta.annotations),
            "relationships": [
                build_relationship("aws::eks::cluster", self.cluster_arn, "belongs_to_cluster")
            ],
            "collected_at":  utc_now(),
        })
        return record

    def _normalize_deployment(self, dep: Any) -> dict[str, Any]:
        meta   = dep.metadata
        spec   = dep.spec or {}
        status = dep.status

        relationships = [
            build_relationship("aws::eks::cluster",       self.cluster_arn,                        "belongs_to_cluster"),
            build_relationship(RESOURCE_TYPE_NAMESPACE,   f"{self.cluster_arn}/{RESOURCE_TYPE_NAMESPACE}/{meta.namespace}", "in_namespace"),
        ]

        record = self._base(RESOURCE_TYPE_DEPLOYMENT, meta.uid, meta.name, meta.namespace)
        record.update({
            "replicas":          getattr(spec, "replicas", None) if hasattr(spec, "replicas") else spec.get("replicas") if isinstance(spec, dict) else None,
            "available_replicas": status.available_replicas if status else None,
            "ready_replicas":    status.ready_replicas if status else None,
            "labels":            dict(meta.labels or {}),
            "selector":          _selector_to_dict(getattr(dep.spec, "selector", None)),
            "containers":        _container_images(dep.spec),
            "relationships":     relationships,
            "collected_at":      utc_now(),
        })
        return record

    def _normalize_service(self, svc: Any) -> dict[str, Any]:
        meta   = svc.metadata
        spec   = svc.spec
        svc_type = getattr(spec, "type", "ClusterIP") if spec else "ClusterIP"

        # For LoadBalancer services, capture the AWS hostname
        lb_hostname = ""
        if svc_type == "LoadBalancer" and svc.status:
            ingress_list = getattr(svc.status.load_balancer, "ingress", None) or []
            if ingress_list:
                lb_hostname = getattr(ingress_list[0], "hostname", "") or getattr(ingress_list[0], "ip", "")

        relationships = [
            build_relationship("aws::eks::cluster",       self.cluster_arn,                        "belongs_to_cluster"),
            build_relationship(RESOURCE_TYPE_NAMESPACE,   f"{self.cluster_arn}/{RESOURCE_TYPE_NAMESPACE}/{meta.namespace}", "in_namespace"),
        ]

        record = self._base(RESOURCE_TYPE_SERVICE, meta.uid, meta.name, meta.namespace)
        record.update({
            "service_type":  svc_type,
            "cluster_ip":    getattr(spec, "cluster_ip", "") if spec else "",
            "lb_hostname":   lb_hostname,
            "ports":         _ports_to_list(spec),
            "selector":      dict(getattr(spec, "selector", {}) or {}),
            "labels":        dict(meta.labels or {}),
            "relationships": relationships,
            "collected_at":  utc_now(),
        })
        return record

    def _normalize_ingress(self, ing: Any) -> dict[str, Any]:
        meta        = ing.metadata
        annotations = dict(meta.annotations or {})

        # ALB hostname is set by AWS Load Balancer Controller on the ingress status
        alb_hostname = ""
        if ing.status and ing.status.load_balancer:
            ingress_list = getattr(ing.status.load_balancer, "ingress", None) or []
            if ingress_list:
                alb_hostname = getattr(ingress_list[0], "hostname", "") or getattr(ingress_list[0], "ip", "")

        # Ingress class — tells us if this is handled by aws-load-balancer-controller
        ingress_class = (
            annotations.get("kubernetes.io/ingress.class", "")
            or (getattr(ing.spec, "ingress_class_name", "") if ing.spec else "")
            or ""
        )

        rules = _ingress_rules(ing.spec)

        relationships = [
            build_relationship("aws::eks::cluster",       self.cluster_arn,                        "belongs_to_cluster"),
            build_relationship(RESOURCE_TYPE_NAMESPACE,   f"{self.cluster_arn}/{RESOURCE_TYPE_NAMESPACE}/{meta.namespace}", "in_namespace"),
        ]

        record = self._base(RESOURCE_TYPE_INGRESS, meta.uid, meta.name, meta.namespace)
        record.update({
            "ingress_class":  ingress_class,
            "alb_hostname":   alb_hostname,
            "rules":          rules,
            "annotations":    _safe_annotations(annotations),
            "labels":         dict(meta.labels or {}),
            "relationships":  relationships,
            "collected_at":   utc_now(),
        })
        return record


# ── Private helpers ────────────────────────────────────────────────────────────

def _safe_annotations(annotations: Any) -> dict[str, str]:
    """Return annotations as a plain dict, stripping values longer than 512 chars."""
    if not annotations:
        return {}
    return {k: (v[:512] if isinstance(v, str) and len(v) > 512 else v) for k, v in dict(annotations).items()}


def _selector_to_dict(selector: Any) -> dict[str, str]:
    if selector is None:
        return {}
    match_labels = getattr(selector, "match_labels", None)
    return dict(match_labels or {})


def _container_images(spec: Any) -> list[str]:
    if spec is None:
        return []
    template = getattr(spec, "template", None)
    if template is None:
        return []
    pod_spec = getattr(template, "spec", None)
    if pod_spec is None:
        return []
    containers = getattr(pod_spec, "containers", []) or []
    return [c.image for c in containers if getattr(c, "image", None)]


def _ports_to_list(spec: Any) -> list[dict[str, Any]]:
    if spec is None:
        return []
    ports = getattr(spec, "ports", []) or []
    result = []
    for p in ports:
        result.append({
            "port":        getattr(p, "port", None),
            "target_port": str(getattr(p, "target_port", "") or ""),
            "protocol":    getattr(p, "protocol", "TCP"),
            "node_port":   getattr(p, "node_port", None),
        })
    return result


def _ingress_rules(spec: Any) -> list[dict[str, Any]]:
    if spec is None:
        return []
    rules = getattr(spec, "rules", []) or []
    result = []
    for rule in rules:
        host = getattr(rule, "host", "") or ""
        paths = []
        http = getattr(rule, "http", None)
        if http:
            for path_item in (getattr(http, "paths", []) or []):
                backend = getattr(path_item, "backend", None)
                svc_name = ""
                svc_port = ""
                if backend:
                    svc = getattr(backend, "service", None)
                    if svc:
                        svc_name = getattr(svc, "name", "")
                        port_obj  = getattr(svc, "port", None)
                        svc_port  = str(getattr(port_obj, "number", "") or getattr(port_obj, "name", "") or "") if port_obj else ""
                paths.append({
                    "path":         getattr(path_item, "path", "/") or "/",
                    "path_type":    getattr(path_item, "path_type", ""),
                    "service_name": svc_name,
                    "service_port": svc_port,
                })
        result.append({"host": host, "paths": paths})
    return result
