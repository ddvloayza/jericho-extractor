from __future__ import annotations

from utils.relationships import build_relationship, merge_relationships


def test_build_relationship():
    rel = build_relationship("aws::ec2::vpc", "vpc-123", "belongs_to_vpc")
    assert rel == {
        "resource_type": "aws::ec2::vpc",
        "resource_id": "vpc-123",
        "relation": "belongs_to_vpc",
    }


def test_merge_relationships_deduplicates():
    r1 = build_relationship("aws::ec2::vpc", "vpc-123", "belongs_to_vpc")
    r2 = build_relationship("aws::ec2::subnet", "subnet-456", "deployed_in_subnet")
    r_dup = build_relationship("aws::ec2::vpc", "vpc-123", "belongs_to_vpc")

    merged = merge_relationships([r1], [r2, r_dup])

    assert len(merged) == 2
    assert r1 in merged
    assert r2 in merged


def test_merge_relationships_preserves_order():
    rels = [
        build_relationship("aws::ec2::vpc", f"vpc-{i}", "rel") for i in range(5)
    ]
    merged = merge_relationships(rels[:3], rels[2:])
    # rels[2] is duplicate — should not be added again
    assert len(merged) == 5
    assert merged[0]["resource_id"] == "vpc-0"


def test_merge_empty_lists():
    assert merge_relationships([], []) == []
    r = build_relationship("aws::ec2::vpc", "vpc-1", "test")
    assert merge_relationships([r], []) == [r]
    assert merge_relationships([], [r]) == [r]
