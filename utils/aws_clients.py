from __future__ import annotations

import logging

import boto3
from botocore.client import BaseClient
from botocore.config import Config as BotocoreConfig

from config import AccountConfig

logger = logging.getLogger(__name__)

_RETRY_CONFIG = BotocoreConfig(
    retries={"max_attempts": 5, "mode": "adaptive"},
    max_pool_connections=50,
)


def get_session(account: AccountConfig) -> boto3.Session:
    """Create a boto3 Session scoped to a specific AWS account."""
    kwargs: dict[str, str] = {
        "aws_access_key_id": account.aws_access_key_id,
        "aws_secret_access_key": account.aws_secret_access_key,
    }
    if account.aws_session_token:
        kwargs["aws_session_token"] = account.aws_session_token
    logger.debug(
        "Creating session for account %s (%s)", account.account_name, account.account_id
    )
    return boto3.Session(**kwargs)


def resolve_identity(session: boto3.Session) -> tuple[str, str]:
    """Call STS GetCallerIdentity and return (account_id, arn)."""
    sts = session.client("sts", config=_RETRY_CONFIG)
    identity = sts.get_caller_identity()
    return identity["Account"], identity["Arn"]


def get_ec2_client(session: boto3.Session, region: str) -> BaseClient:
    return session.client("ec2", region_name=region, config=_RETRY_CONFIG)


def get_elbv2_client(session: boto3.Session, region: str) -> BaseClient:
    return session.client("elbv2", region_name=region, config=_RETRY_CONFIG)
