from __future__ import annotations

from unittest.mock import MagicMock

from collectors.route_tables import RouteTableCollector
from topology.route_analyzer import RouteAnalyzer, RouteTarget

MOCK_RT = {
    "RouteTableId": "rtb-0abc123",
    "VpcId": "vpc-0abc123",
    "Associations": [
        {"Main": False, "SubnetId": "subnet-0abc123"},
    ],
    "Routes": [
        {
            "DestinationCidrBlock": "10.0.0.0/16",
            "GatewayId": "local",
            "State": "active",
            "Origin": "CreateRouteTable",
        },
        {
            "DestinationCidrBlock": "0.0.0.0/0",
            "GatewayId": "igw-0abc123",
            "State": "active",
            "Origin": "CreateRoute",
        },
    ],
    "Tags": [{"Key": "Name", "Value": "public-rt"}],
}


def _make_collector():
    return RouteTableCollector(MagicMock(), "123456789012", "test-account", "us-east-1")


def test_normalize_fields():
    collector = _make_collector()
    result = collector._normalize(MOCK_RT)

    assert result["resource_type"] == "aws::ec2::route_table"
    assert result["resource_id"] == "rtb-0abc123"
    assert result["vpc_id"] == "vpc-0abc123"
    assert result["is_main"] is False
    assert result["associated_subnet_ids"] == ["subnet-0abc123"]
    assert len(result["routes"]) == 2


def test_route_analyzer_detects_igw():
    collector = _make_collector()
    rt = collector._normalize(MOCK_RT)

    analyzer = RouteAnalyzer()
    default_route = analyzer.get_default_route(rt)

    assert default_route is not None
    assert default_route.target_type == RouteTarget.IGW
    assert default_route.target_id == "igw-0abc123"


def test_collect_returns_empty_on_error():
    collector = _make_collector()
    collector.client.get_paginator.side_effect = Exception("error")
    assert collector.collect() == []
