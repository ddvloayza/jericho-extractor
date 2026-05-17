# jericho-extractor

AWS inventory and topology extraction platform. Collects networking and compute resources across multiple accounts and regions, normalizes them into consistent JSON, and builds base topology relationships.

## Requirements

- Python 3.11+
- AWS credentials with read-only access to EC2 and ELBv2

## Setup

```bash
pip install -r requirements.txt
```

## Configuration

### Option 1 — JSON config file (multi-account)

Create a `config.json` file:

```json
{
  "output_dir": "output",
  "log_level": "INFO",
  "accounts": [
    {
      "account_id": "111111111111",
      "account_name": "prod-account",
      "aws_access_key_id": "AKIA...",
      "aws_secret_access_key": "...",
      "regions": ["us-east-1", "us-west-2"]
    },
    {
      "account_id": "222222222222",
      "account_name": "qa-account",
      "aws_access_key_id": "AKIA...",
      "aws_secret_access_key": "...",
      "aws_session_token": "...",
      "regions": ["us-east-1"]
    }
  ]
}
```

Run:

```bash
python main.py --config config.json
```

### Option 2 — Environment variables (single account)

```bash
export AWS_ACCOUNT_ID=111111111111
export AWS_ACCOUNT_NAME=prod-account
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGIONS=us-east-1,us-west-2
export OUTPUT_DIR=output        # optional, default: output
export LOG_LEVEL=INFO           # optional, default: INFO

python main.py
```

## Output structure

```
output/
├── prod-account/
│   ├── vpcs.json
│   ├── subnets.json              ← enriched with subnet_type (public/private/isolated)
│   ├── route_tables.json
│   ├── internet_gateways.json
│   ├── nat_gateways.json
│   ├── transit_gateways.json
│   ├── transit_gateway_attachments.json
│   ├── security_groups.json
│   ├── nacls.json
│   ├── vpc_peerings.json
│   ├── network_interfaces.json
│   ├── vpc_endpoints.json
│   ├── ec2.json
│   ├── load_balancers.json
│   ├── target_groups.json
│   ├── ec2_topology_chains.json  ← EC2 → subnet → route table → gateway chains
│   └── network_graph.json        ← nodes + edges for future graph visualization
│
└── qa-account/
    └── ...
```

## Normalized resource format

Every resource follows this shape:

```json
{
  "resource_type": "aws::ec2::vpc",
  "resource_id": "vpc-0abc123",
  "account_id": "111111111111",
  "account_name": "prod-account",
  "region": "us-east-1",
  "tags": { "Name": "prod-vpc" },
  "relationships": [
    { "resource_type": "aws::ec2::dhcp_options", "resource_id": "dopt-0abc123", "relation": "uses_dhcp" }
  ],
  "collected_at": "2024-01-15T10:30:00+00:00"
}
```

## Collected resources

| Category   | Resource                        |
|------------|---------------------------------|
| Networking | VPC                             |
| Networking | Subnet (with type classification)|
| Networking | Route Table                     |
| Networking | Internet Gateway                |
| Networking | NAT Gateway                     |
| Networking | Transit Gateway                 |
| Networking | Transit Gateway Attachment      |
| Networking | Security Group                  |
| Networking | Network ACL                     |
| Networking | VPC Peering Connection          |
| Networking | Network Interface (ENI)         |
| Networking | VPC Endpoint                    |
| Compute    | EC2 Instance                    |
| Compute    | Load Balancer (ALB/NLB)         |
| Compute    | Target Group                    |

## Subnet classification

Subnets are classified automatically based on their route table:

- **public** — default route (0.0.0.0/0) targets an Internet Gateway
- **private** — default route targets a NAT Gateway or Transit Gateway
- **isolated** — no default route to internet

## Running tests

```bash
python -m pytest tests/ -v
```

## Required IAM permissions

```json
{
  "Effect": "Allow",
  "Action": [
    "ec2:Describe*",
    "elasticloadbalancing:Describe*"
  ],
  "Resource": "*"
}
```
