from __future__ import annotations

RelationshipRecord = dict[str, str]


def build_relationship(
    resource_type: str,
    resource_id: str,
    relation: str,
) -> RelationshipRecord:
    """Build a typed relationship record between two resources."""
    return {
        "resource_type": resource_type,
        "resource_id": resource_id,
        "relation": relation,
    }


def merge_relationships(
    existing: list[RelationshipRecord],
    new: list[RelationshipRecord],
) -> list[RelationshipRecord]:
    """Merge two relationship lists, deduplicating by (type, id, relation)."""
    seen: set[tuple[str, str, str]] = {
        (r["resource_type"], r["resource_id"], r["relation"]) for r in existing
    }
    merged = list(existing)
    for r in new:
        key = (r["resource_type"], r["resource_id"], r["relation"])
        if key not in seen:
            merged.append(r)
            seen.add(key)
    return merged
