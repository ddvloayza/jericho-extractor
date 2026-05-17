from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class OutputWriter:
    """Writes normalized resource data to JSON files organized by account."""

    def __init__(self, base_dir: str = "output") -> None:
        self.base_dir = Path(base_dir)

    def write(
        self,
        account_name: str,
        resource_type: str,
        data: list[dict[str, Any]],
    ) -> Path:
        """Persist data to <base_dir>/<account_name>/<resource_type>.json."""
        account_dir = self.base_dir / account_name
        account_dir.mkdir(parents=True, exist_ok=True)

        file_path = account_dir / f"{resource_type}.json"
        file_path.parent.mkdir(parents=True, exist_ok=True)  # support nested paths
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)

        logger.info(
            "[%s] %s → %d records written to %s",
            account_name,
            resource_type,
            len(data),
            file_path,
        )
        return file_path
