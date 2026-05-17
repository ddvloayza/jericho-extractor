from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AccountConfig:
    aws_access_key_id: str
    aws_secret_access_key: str
    regions: list[str]
    account_id: str = ""
    account_name: str = ""
    aws_session_token: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.regions:
            raise ValueError("AccountConfig must have at least one region.")

    @property
    def is_identity_resolved(self) -> bool:
        return bool(self.account_id)


@dataclass
class AppConfig:
    accounts: list[AccountConfig] = field(default_factory=list)
    output_dir: str = "output"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> AppConfig:
        """Load a single account from environment variables.

        AWS_ACCOUNT_ID and AWS_ACCOUNT_NAME are optional — if omitted they
        are resolved automatically via STS GetCallerIdentity at runtime.
        """
        account = AccountConfig(
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
            regions=os.environ.get("AWS_REGIONS", "us-east-1").split(","),
            account_id=os.environ.get("AWS_ACCOUNT_ID", ""),
            account_name=os.environ.get("AWS_ACCOUNT_NAME", ""),
        )
        return cls(
            accounts=[account],
            output_dir=os.environ.get("OUTPUT_DIR", "output"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )

    @classmethod
    def from_file(cls, path: str) -> AppConfig:
        """Load multi-account config from a JSON file."""
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        accounts = [AccountConfig(**a) for a in raw["accounts"]]
        return cls(
            accounts=accounts,
            output_dir=raw.get("output_dir", "output"),
            log_level=raw.get("log_level", "INFO"),
        )
