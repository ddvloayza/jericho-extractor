from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from models.base_resource import BaseResource


@dataclass
class VPCResource(BaseResource):
    cidr_block: str = ""
    state: str = ""
    is_default: bool = False
    dhcp_options_id: str = ""
    instance_tenancy: str = ""
    cidr_block_associations: list[str] = field(default_factory=list)
    ipv6_cidr_blocks: list[str] = field(default_factory=list)


@dataclass
class SubnetResource(BaseResource):
    vpc_id: str = ""
    cidr_block: str = ""
    availability_zone: str = ""
    available_ip_count: int = 0
    state: str = ""
    is_default: bool = False
    map_public_ip_on_launch: bool = False
    subnet_type: str = "unknown"  # public / private / isolated


@dataclass
class RouteTableResource(BaseResource):
    vpc_id: str = ""
    is_main: bool = False
    associated_subnet_ids: list[str] = field(default_factory=list)
    routes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class InternetGatewayResource(BaseResource):
    state: str = ""
    attached_vpc_ids: list[str] = field(default_factory=list)


@dataclass
class NatGatewayResource(BaseResource):
    vpc_id: str = ""
    subnet_id: str = ""
    state: str = ""
    connectivity_type: str = ""
    public_ip: str = ""
    private_ip: str = ""


@dataclass
class TransitGatewayResource(BaseResource):
    state: str = ""
    owner_id: str = ""
    description: str = ""
    amazon_side_asn: Optional[int] = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class TransitGatewayAttachmentResource(BaseResource):
    transit_gateway_id: str = ""
    attachment_type: str = ""
    state: str = ""
    resource_id: str = ""
    resource_owner_id: str = ""
    transit_gateway_owner_id: str = ""


@dataclass
class SecurityGroupResource(BaseResource):
    vpc_id: str = ""
    group_name: str = ""
    description: str = ""
    inbound_rules: list[dict[str, Any]] = field(default_factory=list)
    outbound_rules: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class NACLResource(BaseResource):
    vpc_id: str = ""
    is_default: bool = False
    associated_subnet_ids: list[str] = field(default_factory=list)
    inbound_rules: list[dict[str, Any]] = field(default_factory=list)
    outbound_rules: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class VPCPeeringResource(BaseResource):
    status: str = ""
    requester_vpc_id: str = ""
    requester_account_id: str = ""
    requester_region: str = ""
    accepter_vpc_id: str = ""
    accepter_account_id: str = ""
    accepter_region: str = ""


@dataclass
class NetworkInterfaceResource(BaseResource):
    vpc_id: str = ""
    subnet_id: str = ""
    interface_type: str = ""
    status: str = ""
    private_ip_address: str = ""
    public_ip_address: str = ""
    attachment_instance_id: str = ""
    description: str = ""
    security_group_ids: list[str] = field(default_factory=list)


@dataclass
class VPCEndpointResource(BaseResource):
    vpc_id: str = ""
    service_name: str = ""
    endpoint_type: str = ""
    state: str = ""
    associated_subnet_ids: list[str] = field(default_factory=list)
    associated_route_table_ids: list[str] = field(default_factory=list)
