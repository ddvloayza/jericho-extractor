# Inventory Model

## Base schema (all resources)

| Field          | Type            | Description                          |
|----------------|-----------------|--------------------------------------|
| resource_type  | string          | e.g. `aws::ec2::vpc`                 |
| resource_id    | string          | Primary AWS identifier               |
| account_id     | string          | 12-digit AWS account ID              |
| account_name   | string          | Human-readable account name          |
| region         | string          | AWS region                           |
| tags           | object          | Key-value tag map                    |
| relationships  | array           | Typed edges to other resources       |
| collected_at   | ISO 8601 string | UTC timestamp of collection          |

## Resource-specific fields

### VPC
`cidr_block`, `state`, `is_default`, `dhcp_options_id`, `instance_tenancy`, `cidr_block_associations`, `ipv6_cidr_blocks`

### Subnet
`vpc_id`, `cidr_block`, `availability_zone`, `available_ip_count`, `state`, `is_default`, `map_public_ip_on_launch`, `subnet_type` *(public/private/isolated/unknown)*

### Route Table
`vpc_id`, `is_main`, `associated_subnet_ids`, `routes[]`

Each route: `destination_cidr`, `gateway_id`, `nat_gateway_id`, `transit_gateway_id`, `vpc_peering_connection_id`, `state`, `origin`

### Security Group
`vpc_id`, `group_name`, `description`, `inbound_rules[]`, `outbound_rules[]`

Each rule: `protocol`, `from_port`, `to_port`, `ipv4_ranges[]`, `ipv6_ranges[]`, `referenced_group_ids[]`, `prefix_list_ids[]`

### Network ACL
`vpc_id`, `is_default`, `associated_subnet_ids`, `inbound_rules[]`, `outbound_rules[]`

Each entry: `rule_number`, `protocol`, `rule_action`, `cidr_block`, `from_port`, `to_port`

### EC2 Instance
`instance_type`, `state`, `vpc_id`, `subnet_id`, `private_ip`, `public_ip`, `availability_zone`, `ami_id`, `key_name`, `platform`, `security_group_ids[]`, `iam_instance_profile`, `launch_time`

### Load Balancer
`dns_name`, `scheme`, `lb_type`, `state`, `vpc_id`, `availability_zones[]`, `security_group_ids[]`

### Target Group
`protocol`, `port`, `vpc_id`, `target_type`, `health_check_protocol`, `health_check_path`, `load_balancer_arns[]`, `targets[]`
