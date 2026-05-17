# Future Roadmap

## Phase 2 — Storage & querying
- S3 output (versioned inventory snapshots)
- Athena queries over S3 JSON
- DynamoDB for live inventory state

## Phase 3 — Automation
- Lambda execution mode
- EventBridge scheduled runs
- Step Functions for multi-account orchestration

## Phase 4 — Graph topology
- Neptune or Neo4j ingestion from `network_graph.json`
- Shortest-path queries between resources
- Blast-radius analysis

## Phase 5 — Additional collectors
- RDS instances and subnet groups
- ElastiCache clusters
- EKS clusters and node groups
- Lambda functions (VPC-attached)
- CloudFront distributions
- Route53 hosted zones
- Direct Connect / VPN connections
- AWS RAM shared resources

## Phase 6 — Visualization
- D3.js or Cytoscape topology renderer
- Web UI for browsing inventory
- Diff view between inventory snapshots

## Phase 7 — Intelligence
- Anomaly detection on network changes
- Security posture scoring (open SGs, public subnets with sensitive EC2)
- Cost attribution by VPC/subnet
