# Architecture

## Overview

```
main.py
  └── per account × region:
        ├── utils/aws_clients.py   → boto3 session + clients
        ├── collectors/            → raw AWS API → normalized dicts
        ├── topology/              → enrichment (subnet type, chains, graph)
        └── utils/writer.py        → JSON files on disk
```

## Layers

### config.py
Holds `AccountConfig` (credentials + regions) and `AppConfig` (accounts list, output dir, log level). Supports JSON file or environment variable loading.

### utils/
- `aws_clients.py` — creates boto3 Sessions and EC2/ELBv2 clients, injected into collectors
- `helpers.py` — generic paginator, tag normalizer, UTC timestamp
- `writer.py` — `OutputWriter` serializes resource lists to `output/<account>/<type>.json`
- `relationships.py` — typed relationship records, deduplication

### collectors/
One class per AWS resource type. Each class:
1. Receives an injected boto3 client + account context
2. Calls `collect()` → paginates the AWS API
3. Calls `_normalize(raw)` → returns a consistent dict conforming to the base schema

### models/
Python dataclasses mirroring the normalized schema. Used as documentation and for optional strict construction. Collectors return plain dicts for simplicity.

### topology/
- `route_analyzer.py` — parses routes, resolves target type (IGW/NAT/TGW/...)
- `subnet_classifier.py` — classifies subnets as public/private/isolated
- `dependency_mapper.py` — builds EC2 → subnet → route table → gateway chains
- `network_graph.py` — builds nodes + edges structure ready for future graph DB ingestion

### schemas/
JSON Schema definitions for each major resource type. Used for validation and documentation.
