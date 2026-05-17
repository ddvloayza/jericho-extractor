from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Generator

logger = logging.getLogger(__name__)


def normalize_tags(tags: list[dict[str, str]] | None) -> dict[str, str]:
    """Convert AWS Tags list [{"Key": k, "Value": v}] to a plain dict."""
    if not tags:
        return {}
    return {t["Key"]: t["Value"] for t in tags}


def utc_now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def paginate(client: Any, method: str, result_key: str, **kwargs: Any) -> list[Any]:
    """
    Generic AWS paginator.
    Falls back to direct call when the operation does not support pagination.
    """
    try:
        paginator = client.get_paginator(method)
        results: list[Any] = []
        for page in paginator.paginate(**kwargs):
            results.extend(page.get(result_key, []))
        return results
    except Exception as exc:
        logger.debug("Paginator unavailable for %s, using direct call: %s", method, exc)
        response = getattr(client, method)(**kwargs)
        return response.get(result_key, [])


def chunks(lst: list[Any], size: int) -> Generator[list[Any], None, None]:
    """Yield successive fixed-size chunks from a list."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]
