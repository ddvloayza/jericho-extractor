from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::instance"


class EC2Collector:
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
        logger.info("[%s][%s] Collecting EC2 Instances", self.account_name, self.region)
        try:
            reservations = paginate(self.client, "describe_instances", "Reservations")
            instances: list[dict[str, Any]] = []
            for reservation in reservations:
                for instance in reservation.get("Instances", []):
                    instances.append(self._normalize(instance))
            return instances
        except Exception as exc:
            logger.error(
                "[%s][%s] EC2 Instances failed: %s", self.account_name, self.region, exc
            )
            return []

    def _normalize(self, instance: dict[str, Any]) -> dict[str, Any]:
        instance_id = instance["InstanceId"]
        vpc_id = instance.get("VpcId", "")
        subnet_id = instance.get("SubnetId", "")
        sg_ids = [sg["GroupId"] for sg in instance.get("SecurityGroups", [])]

        public_ip = instance.get("PublicIpAddress", "") or ""
        private_ip = instance.get("PrivateIpAddress", "") or ""

        iam_profile = ""
        if profile := instance.get("IamInstanceProfile"):
            iam_profile = profile.get("Arn", "")

        relationships = []
        if vpc_id:
            relationships.append(build_relationship("aws::ec2::vpc", vpc_id, "deployed_in_vpc"))
        if subnet_id:
            relationships.append(
                build_relationship("aws::ec2::subnet", subnet_id, "deployed_in_subnet")
            )
        for sg_id in sg_ids:
            relationships.append(
                build_relationship("aws::ec2::security_group", sg_id, "protected_by_sg")
            )

        return {
            "resource_type": RESOURCE_TYPE,
            "resource_id": instance_id,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "region": self.region,
            "instance_type": instance.get("InstanceType", ""),
            "state": instance.get("State", {}).get("Name", ""),
            "vpc_id": vpc_id,
            "subnet_id": subnet_id,
            "private_ip": private_ip,
            "public_ip": public_ip,
            "availability_zone": instance.get("Placement", {}).get("AvailabilityZone", ""),
            "ami_id": instance.get("ImageId", ""),
            "key_name": instance.get("KeyName", ""),
            "platform": instance.get("Platform", "linux"),
            "architecture": instance.get("Architecture", ""),
            "security_group_ids": sg_ids,
            "iam_instance_profile": iam_profile,
            "launch_time": str(instance.get("LaunchTime", "")),
            "tags": normalize_tags(instance.get("Tags")),
            "relationships": relationships,
            "collected_at": utc_now(),
        }
