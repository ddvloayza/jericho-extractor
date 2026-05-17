from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::rds::dbinstance"


class RDSCollector:
    """Collect RDS DB instances with networking and encryption metadata."""

    def __init__(
        self,
        client: BaseClient,
        account_id: str,
        account_name: str,
        region: str,
    ) -> None:
        self.client = client
        self.account_id = account_id
        self.account_name = account_name
        self.region = region

    def collect(self) -> list[dict[str, Any]]:
        logger.info("[%s][%s] Collecting RDS instances", self.account_name, self.region)
        try:
            instances = paginate(self.client, "describe_db_instances", "DBInstances")
            return [self._normalize(db) for db in instances]
        except Exception as exc:
            logger.error(
                "[%s][%s] RDS instances failed: %s", self.account_name, self.region, exc
            )
            return []

    def _normalize(self, db: dict[str, Any]) -> dict[str, Any]:
        db_arn        = db["DBInstanceArn"]
        db_id         = db["DBInstanceIdentifier"]
        kms_key_id    = db.get("KmsKeyId", "")
        subnet_group  = db.get("DBSubnetGroup") or {}
        sg_list       = db.get("VpcSecurityGroups") or []
        sg_ids        = [sg["VpcSecurityGroupId"] for sg in sg_list if sg.get("Status") == "active"]
        endpoint      = db.get("Endpoint") or {}
        subnet_group_name = subnet_group.get("DBSubnetGroupName", "")

        # Subnet IDs from the subnet group
        subnet_ids = [
            s["SubnetIdentifier"]
            for s in subnet_group.get("Subnets") or []
            if s.get("SubnetIdentifier")
        ]

        relationships: list[dict[str, str]] = []
        if subnet_group_name:
            relationships.append(
                build_relationship("aws::rds::subnetgroup", subnet_group_name, "deployed_in_subnet_group")
            )
        for sid in subnet_ids:
            relationships.append(build_relationship("aws::ec2::subnet", sid, "deployed_in_subnet"))
        for sg_id in sg_ids:
            relationships.append(build_relationship("aws::ec2::security_group", sg_id, "protected_by_sg"))
        if kms_key_id:
            relationships.append(build_relationship("aws::kms::key", kms_key_id, "encrypted_by_kms"))

        tags = self._fetch_tags(db_arn)

        return {
            "resource_type":        RESOURCE_TYPE,
            "resource_id":          db_arn,
            "resource_name":        db_id,
            "account_id":           self.account_id,
            "account_name":         self.account_name,
            "region":               self.region,
            "engine":               db.get("Engine", ""),
            "engine_version":       db.get("EngineVersion", ""),
            "instance_class":       db.get("DBInstanceClass", ""),
            "status":               db.get("DBInstanceStatus", ""),
            "allocated_storage_gb": db.get("AllocatedStorage", 0),
            "multi_az":             db.get("MultiAZ", False),
            "publicly_accessible":  db.get("PubliclyAccessible", False),
            "storage_encrypted":    db.get("StorageEncrypted", False),
            "kms_key_id":           kms_key_id,
            "subnet_group_name":    subnet_group_name,
            "vpc_id":               subnet_group.get("VpcId", ""),
            "subnet_ids":           subnet_ids,
            "security_group_ids":   sg_ids,
            "endpoint_address":     endpoint.get("Address", ""),
            "endpoint_port":        endpoint.get("Port", 0),
            "backup_retention_days": db.get("BackupRetentionPeriod", 0),
            "deletion_protection":  db.get("DeletionProtection", False),
            "availability_zone":    db.get("AvailabilityZone", ""),
            "secondary_az":         db.get("SecondaryAvailabilityZone", ""),
            "auto_minor_version_upgrade": db.get("AutoMinorVersionUpgrade", False),
            "ca_certificate":       db.get("CACertificateIdentifier", ""),
            "instance_create_time": str(db.get("InstanceCreateTime", "")),
            "tags":                 tags,
            "relationships":        relationships,
            "collected_at":         utc_now(),
        }

    def _fetch_tags(self, arn: str) -> dict[str, str]:
        try:
            response = self.client.list_tags_for_resource(ResourceName=arn)
            return {t["Key"]: t["Value"] for t in response.get("TagList") or []}
        except Exception:
            return {}
