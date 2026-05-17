from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.base_resource import BaseResource


@dataclass
class EC2Resource(BaseResource):
    instance_type: str = ""
    state: str = ""
    vpc_id: str = ""
    subnet_id: str = ""
    private_ip: str = ""
    public_ip: str = ""
    availability_zone: str = ""
    ami_id: str = ""
    key_name: str = ""
    platform: str = ""
    security_group_ids: list[str] = field(default_factory=list)
    iam_instance_profile: str = ""
    launch_time: str = ""


@dataclass
class LoadBalancerResource(BaseResource):
    dns_name: str = ""
    scheme: str = ""
    lb_type: str = ""
    state: str = ""
    vpc_id: str = ""
    availability_zones: list[dict[str, Any]] = field(default_factory=list)
    security_group_ids: list[str] = field(default_factory=list)


@dataclass
class TargetGroupResource(BaseResource):
    protocol: str = ""
    port: int = 0
    vpc_id: str = ""
    target_type: str = ""
    health_check_protocol: str = ""
    health_check_path: str = ""
    load_balancer_arns: list[str] = field(default_factory=list)
    targets: list[dict[str, Any]] = field(default_factory=list)
