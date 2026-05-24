from __future__ import annotations

import base64
import logging

import boto3
from botocore.auth import SigV4QueryAuth
from botocore.awsrequest import AWSRequest
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


def resolve_account_name(session: boto3.Session, account_id: str) -> str:
    """Try to get the friendly account name from AWS Organizations.

    Requires organizations:DescribeAccount permission on the management account
    or a delegated admin. Falls back to the account_id string if denied.
    """
    try:
        org = session.client("organizations", region_name="us-east-1", config=_RETRY_CONFIG)
        resp = org.describe_account(AccountId=account_id)
        name = resp["Account"].get("Name", "").strip()
        if name:
            logger.info("Resolved account name from Organizations: %s", name)
            return name
    except Exception as exc:
        logger.debug("Could not resolve account name from Organizations: %s", exc)
    return account_id


def get_ec2_client(session: boto3.Session, region: str) -> BaseClient:
    return session.client("ec2", region_name=region, config=_RETRY_CONFIG)


def get_elbv2_client(session: boto3.Session, region: str) -> BaseClient:
    return session.client("elbv2", region_name=region, config=_RETRY_CONFIG)


def get_eks_client(session: boto3.Session, region: str) -> BaseClient:
    return session.client("eks", region_name=region, config=_RETRY_CONFIG)


def get_lambda_client(session: boto3.Session, region: str) -> BaseClient:
    return session.client("lambda", region_name=region, config=_RETRY_CONFIG)


def get_rds_client(session: boto3.Session, region: str) -> BaseClient:
    return session.client("rds", region_name=region, config=_RETRY_CONFIG)


def get_iam_client(session: boto3.Session) -> BaseClient:
    return session.client("iam", config=_RETRY_CONFIG)


def get_kms_client(session: boto3.Session, region: str) -> BaseClient:
    return session.client("kms", region_name=region, config=_RETRY_CONFIG)


def get_secretsmanager_client(session: boto3.Session, region: str) -> BaseClient:
    return session.client("secretsmanager", region_name=region, config=_RETRY_CONFIG)


def get_s3_client(session: boto3.Session) -> BaseClient:
    return session.client("s3", config=_RETRY_CONFIG)


def get_eks_bearer_token(cluster_name: str, session: boto3.Session, region: str) -> str:
    """Generate a bearer token for authenticating to an EKS cluster's Kubernetes API.

    Uses a presigned STS GetCallerIdentity URL signed with SigV4, which EKS
    validates server-side. Token is prefixed with 'k8s-aws-v1.' as required.
    Token is valid for 60 seconds (EKS accepts up to 15 minutes).
    """
    credentials = session.get_credentials().get_frozen_credentials()
    url = f"https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15"
    request = AWSRequest(method="GET", url=url, headers={"x-k8s-aws-id": cluster_name})
    SigV4QueryAuth(credentials, "sts", region, expires=60).add_auth(request)
    token = "k8s-aws-v1." + base64.urlsafe_b64encode(
        request.url.encode()
    ).decode().rstrip("=")
    return token
