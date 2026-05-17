from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BaseResource:
    """Minimum normalized shape every AWS resource must conform to."""

    resource_type: str
    resource_id: str
    account_id: str
    account_name: str
    region: str
    tags: dict[str, str] = field(default_factory=dict)
    relationships: list[dict[str, str]] = field(default_factory=list)
    collected_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
