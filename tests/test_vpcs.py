from __future__ import annotations

from unittest.mock import MagicMock, patch

from collectors.vpcs import VPCCollector

MOCK_VPC = {
    "VpcId": "vpc-0abc123",
    "CidrBlock": "10.0.0.0/16",
    "State": "available",
    "IsDefault": False,
    "DhcpOptionsId": "dopt-0abc123",
    "InstanceTenancy": "default",
    "CidrBlockAssociationSet": [{"CidrBlock": "10.0.0.0/16"}],
    "Ipv6CidrBlockAssociationSet": [],
    "Tags": [{"Key": "Name", "Value": "my-vpc"}],
}


def _make_collector():
    client = MagicMock()
    return VPCCollector(client, "123456789012", "test-account", "us-east-1")


def test_normalize_fields():
    collector = _make_collector()
    result = collector._normalize(MOCK_VPC)

    assert result["resource_type"] == "aws::ec2::vpc"
    assert result["resource_id"] == "vpc-0abc123"
    assert result["cidr_block"] == "10.0.0.0/16"
    assert result["state"] == "available"
    assert result["is_default"] is False
    assert result["tags"] == {"Name": "my-vpc"}
    assert result["account_id"] == "123456789012"
    assert result["account_name"] == "test-account"
    assert result["region"] == "us-east-1"


def test_relationships_include_dhcp():
    collector = _make_collector()
    result = collector._normalize(MOCK_VPC)

    rels = result["relationships"]
    assert any(r["resource_id"] == "dopt-0abc123" for r in rels)
    assert any(r["relation"] == "uses_dhcp" for r in rels)


def test_collect_returns_empty_on_error():
    collector = _make_collector()
    collector.client.get_paginator.side_effect = Exception("Access denied")
    result = collector.collect()
    assert result == []


def test_collect_returns_list():
    collector = _make_collector()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [{"Vpcs": [MOCK_VPC]}]
    collector.client.get_paginator.return_value = mock_paginator

    result = collector.collect()
    assert len(result) == 1
    assert result[0]["resource_id"] == "vpc-0abc123"
