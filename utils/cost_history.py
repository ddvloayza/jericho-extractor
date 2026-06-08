"""
Cost history accumulator.

Merges new Cost Explorer records into a persistent costs_history_<key>.json
file so data older than the CE 90-day lookback window is never lost.

Merge strategy (per file):
  - For every date present in the NEW batch → replace all old records for
    that date (fresh data wins, no duplicates).
  - For every date NOT in the new batch    → keep old records untouched.
  - Result is sorted ascending by date.

Usage:
    from utils.cost_history import merge_and_save

    merge_and_save(
        new_records  = cost_data["costs_daily"],
        history_path = account_dir / "costs_history.json",
        date_key     = "date",
    )
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def merge_and_save(
    new_records:  list[dict[str, Any]],
    history_path: Path,
    date_key:     str = "date",
) -> list[dict[str, Any]]:
    """
    Merge new_records into history_path and write the result back.
    Returns the merged list.
    """
    # Load existing history
    existing: list[dict[str, Any]] = []
    if history_path.exists():
        try:
            existing = json.loads(history_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not read cost history %s: %s — starting fresh", history_path, exc)

    # Dates covered by new batch
    new_dates: set[str] = {r[date_key] for r in new_records if r.get(date_key)}

    # Keep old records whose date is NOT in the new batch
    kept_old = [r for r in existing if r.get(date_key) not in new_dates]

    # Merge and sort
    merged = sorted(kept_old + new_records, key=lambda r: r.get(date_key, ""))

    # Write back
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=None),
        encoding="utf-8",
    )

    added   = len(new_records)
    kept    = len(kept_old)
    total   = len(merged)
    date_range = f"{merged[0][date_key]} → {merged[-1][date_key]}" if merged else "empty"
    logger.info(
        "Cost history %s: +%d new, %d kept, %d total (%s)",
        history_path.name, added, kept, total, date_range,
    )
    return merged
