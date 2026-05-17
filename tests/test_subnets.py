from __future__ import annotations

from unittest.mock import MagicMock

from collectors.subnets import SubnetCollector

MOCK_SUBNET = {
    "SubnetId": "subnet-0abc123",
    "VpcId": "vpc-0abc123",
    "CidrBlock": "10.0.1.0/24",
    "AvailabilityZone": "us-east-1a",
    "AvailabilityZoneId": "use1-az1",
    "AvailableIpAddressCount": 251,
    "State": "available",
    "DefaultForAz": False,
    "MapPublicIpOnLaunch": False,
    "Tags": [{"Key": "Name", "Value": "private-subnet-1"}],
}


def _make_collector():
    return SubnetCollector(MagicMock(), "123456789012", "test-account", "us-east-1")


def test_normalize_fields():
    collector = _make_collector()
    result = collector._normalize(MOCK_SUBNET)

    assert result["resource_type"] == "aws::ec2::subnet"
    assert result["resource_id"] == "subnet-0abc123"
    assert result["vpc_id"] == "vpc-0abc123"
    assert result["cidr_block"] == "10.0.1.0/24"
    assert result["availability_zone"] == "us-east-1a"
    assert result["available_ip_count"] == 251
    assert result["subnet_type"] == "unknown"
    assert result["tags"] == {"Name": "private-subnet-1"}


def test_relationship_to_vpc():
    collector = _make_collector()
    result = collector._normalize(MOCK_SUBNET)

    rels = result["relationships"]
    assert any(
        r["resource_type"] == "aws::ec2::vpc" and r["resource_id"] == "vpc-0abc123"
        for r in rels
    )


def test_collect_returns_empty_on_error():
    collector = _make_collector()
    collector.client.get_paginator.side_effect = Exception("throttled")
    assert collector.collect() == []
