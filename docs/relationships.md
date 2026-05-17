# Relationships

Every normalized resource contains a `relationships` array. Each entry:

```json
{
  "resource_type": "aws::ec2::vpc",
  "resource_id": "vpc-0abc123",
  "relation": "belongs_to_vpc"
}
```

## Relationship catalog

| Source                  | Target                  | Relation                    |
|-------------------------|-------------------------|-----------------------------|
| VPC                     | DHCP Options            | uses_dhcp                   |
| Subnet                  | VPC                     | belongs_to_vpc              |
| Route Table             | VPC                     | belongs_to_vpc              |
| Route Table             | Subnet                  | associated_with_subnet      |
| Internet Gateway        | VPC                     | attached_to_vpc             |
| NAT Gateway             | VPC                     | belongs_to_vpc              |
| NAT Gateway             | Subnet                  | deployed_in_subnet          |
| TGW Attachment          | Transit Gateway         | attached_to_tgw             |
| TGW Attachment          | VPC                     | attachment_resource         |
| Security Group          | VPC                     | belongs_to_vpc              |
| NACL                    | VPC                     | belongs_to_vpc              |
| NACL                    | Subnet                  | associated_with_subnet      |
| VPC Peering             | VPC (requester)         | requester_vpc               |
| VPC Peering             | VPC (accepter)          | accepter_vpc                |
| ENI                     | VPC                     | belongs_to_vpc              |
| ENI                     | Subnet                  | deployed_in_subnet          |
| ENI                     | EC2 Instance            | attached_to_instance        |
| VPC Endpoint            | VPC                     | belongs_to_vpc              |
| VPC Endpoint            | Subnet                  | deployed_in_subnet          |
| EC2 Instance            | VPC                     | deployed_in_vpc             |
| EC2 Instance            | Subnet                  | deployed_in_subnet          |
| EC2 Instance            | Security Group          | protected_by_sg             |
| Load Balancer           | VPC                     | deployed_in_vpc             |
| Load Balancer           | Subnet                  | deployed_in_subnet          |
| Load Balancer           | Security Group          | protected_by_sg             |
| Target Group            | VPC                     | belongs_to_vpc              |
| Target Group            | Load Balancer           | registered_on_lb            |
