from __future__ import annotations

import logging
from typing import Any

from botocore.client import BaseClient

from utils.helpers import normalize_tags, paginate, utc_now
from utils.relationships import build_relationship

logger = logging.getLogger(__name__)

RESOURCE_TYPE = "aws::ec2::network_interface"


class NetworkInterfaceCollector:
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
        logger.info(
            "[%s][%s] Collecting Network Interfaces", self.account_name, self.region
        )
        try:
            enis = paginate(
                self.client, "describe_network_interfaces", "NetworkInterfaces"
            )
            return [self._normalize(e) for e in enis]
        except Exception as exc:
            logger.error(
                "[%s][%s] Network Interfaces failed: %s", self.account_name, self.region, exc
            )
            return []

    def _normalize(self, eni: dict[str, Any]) -> dict[str, Any]:
        eni_id = eni["NetworkInterfaceId"]
        vpc_id = eni.get("VpcId", "")
        subnet_id = eni.get("SubnetId", "")
        attachment = eni.get("Attachment", {})
        instance_id = attachment.get("InstanceId", "")

        association = eni.get("Association", {})
        public_ip = association.get("PublicIp", "")

        sg_ids = [g["GroupId"] for g in eni.get("Groups", [])]

        relationships = []
        if vpc_id:
            relationships.append(build_relationship("aws::ec2::vpc", vpc_id, "belongs_to_vpc"))
        if subnet_id:
            relationships.append(
                build_relationship("aws::ec2::subnet", subnet_id, "deployed_in_subnet")
            )
        if instance_id:
            relationships.append(
                build_relationship("aws::ec2::instance", instance_id, "attached_to_instance")
            )

        return {
            "resource_type": RESOURCE_TYPE,
            "resource_id": eni_id,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "region": self.region,
            "vpc_id": vpc_id,
            "subnet_id": subnet_id,
            "interface_type": eni.get("InterfaceType", ""),
            "status": eni.get("Status", ""),
            "private_ip_address": eni.get("PrivateIpAddress", ""),
            "public_ip_address": public_ip,
            "attachment_instance_id": instance_id,
            "attachment_status": attachment.get("Status", ""),
            "description": eni.get("Description", ""),
            "security_group_ids": sg_ids,
            "availability_zone": eni.get("AvailabilityZone", ""),
            "tags": normalize_tags(eni.get("TagSet")),
            "relationships": relationships,
            "collected_at": utc_now(),
        }
