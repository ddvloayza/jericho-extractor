"""
API Gateway collector — covers both REST APIs (v1) and HTTP/WebSocket APIs (v2).

With many Lambdas named like *-lmbd-exchange-rates or *-lmbd-payments,
these are commonly fronted by an API Gateway that wasn't otherwise visible
in the inventory.

Output file: api_gateway.json  (mixed resource_type: restapi + apigatewayv2)

Required IAM permissions (read-only):
  apigateway:GET
  apigateway:GetTags  (covered by GET on the tags path)
"""
from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now

logger = logging.getLogger(__name__)

REST_RESOURCE_TYPE = "aws::apigateway::restapi"
V2_RESOURCE_TYPE   = "aws::apigatewayv2::api"


class APIGatewayCollector:
    def __init__(
        self,
        rest_client: BaseClient,
        v2_client: BaseClient,
        account_id: str,
        account_name: str,
        region: str,
    ) -> None:
        self.rest_client  = rest_client
        self.v2_client    = v2_client
        self.account_id   = account_id
        self.account_name = account_name
        self.region       = region

    def collect(self) -> list[dict[str, Any]]:
        logger.info("[%s][%s] Collecting API Gateway (REST + HTTP/WebSocket)", self.account_name, self.region)
        results: list[dict[str, Any]] = []
        results.extend(self._collect_rest_apis())
        results.extend(self._collect_v2_apis())
        return results

    def _collect_rest_apis(self) -> list[dict[str, Any]]:
        try:
            apis = paginate(self.rest_client, "get_rest_apis", "items")
        except Exception as exc:
            logger.error("[%s][%s] REST APIs failed: %s", self.account_name, self.region, exc)
            return []
        return [self._normalize_rest(a) for a in apis]

    def _normalize_rest(self, api: dict[str, Any]) -> dict[str, Any]:
        endpoint_cfg = api.get("endpointConfiguration", {}) or {}
        return {
            "resource_type":       REST_RESOURCE_TYPE,
            "resource_id":         api.get("id", ""),
            "resource_name":       api.get("name", ""),
            "account_id":          self.account_id,
            "account_name":        self.account_name,
            "region":              self.region,
            "description":        api.get("description", ""),
            "created_date":        str(api.get("createdDate", "")),
            "endpoint_types":      endpoint_cfg.get("types", []),
            "api_key_source":      api.get("apiKeySource", ""),
            "disable_execute_api": api.get("disableExecuteApiEndpoint", False),
            "tags":                api.get("tags", {}) or {},
            "collected_at":        utc_now(),
        }

    def _collect_v2_apis(self) -> list[dict[str, Any]]:
        try:
            apis = paginate(self.v2_client, "get_apis", "Items")
        except Exception as exc:
            logger.error("[%s][%s] HTTP/WebSocket APIs failed: %s", self.account_name, self.region, exc)
            return []
        return [self._normalize_v2(a) for a in apis]

    def _normalize_v2(self, api: dict[str, Any]) -> dict[str, Any]:
        return {
            "resource_type":       V2_RESOURCE_TYPE,
            "resource_id":         api.get("ApiId", ""),
            "resource_name":       api.get("Name", ""),
            "account_id":          self.account_id,
            "account_name":        self.account_name,
            "region":              self.region,
            "protocol_type":       api.get("ProtocolType", ""),   # "HTTP" or "WEBSOCKET"
            "description":         api.get("Description", ""),
            "created_date":        str(api.get("CreatedDate", "")),
            "api_endpoint":        api.get("ApiEndpoint", ""),
            "disable_execute_api": api.get("DisableExecuteApiEndpoint", False),
            "tags":                api.get("Tags", {}) or {},
            "collected_at":        utc_now(),
        }
