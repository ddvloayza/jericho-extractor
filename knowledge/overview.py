"""Documento indice de la cuenta: que hay y en que archivo buscarlo.

Es lo primero que conviene leer antes de abrir un documento de detalle -- da
el panorama y dice donde esta cada cosa, sin cargar los archivos grandes.
"""
from __future__ import annotations

from pathlib import Path

from .common import GraphBuilder, load, of_type, write_doc

# (archivo json, etiqueta, documento donde se detalla)
INVENTORY = [
    ("ec2.json", "Instancias EC2", "compute.md"),
    ("security_groups.json", "Security groups", "compute.md"),
    ("vpcs.json", "VPCs", "network.md"),
    ("subnets.json", "Subnets", "network.md"),
    ("route_tables.json", "Tablas de ruteo", "network.md"),
    ("vpc_endpoints.json", "VPC endpoints", "network.md"),
    ("transit_gateway_attachments.json", "Attachments a transit gateway", "network.md"),
    ("rds.json", "Bases de datos RDS", "data.md"),
    ("s3_buckets.json", "Buckets S3", "data.md"),
    ("dynamodb.json", "Tablas DynamoDB", "data.md"),
    ("ebs.json", "Volumenes EBS", "data.md"),
    ("ecr.json", "Repositorios ECR", "data.md"),
    ("lambdas.json", "Funciones Lambda", "workloads.md"),
    ("load_balancers.json", "Balanceadores", "workloads.md"),
    ("sqs.json", "Colas SQS", "workloads.md"),
    ("sns.json", "Topicos SNS", "workloads.md"),
    ("api_gateway.json", "APIs", "workloads.md"),
    ("iam_roles.json", "Roles IAM", "security.md"),
    ("iam_users.json", "Usuarios IAM", "security.md"),
    ("kms.json", "Claves KMS", "security.md"),
    ("secrets.json", "Secretos", "security.md"),
    ("acm.json", "Certificados ACM", "security.md"),
]


def build(account: str, src: Path, dest: Path) -> Path | None:
    counts: list[tuple[str, int, str]] = []
    for filename, label, doc in INVENTORY:
        items = load(src / filename)
        if items:
            counts.append((label, len(items), doc))

    if not counts:
        return None

    # El account_id sale de cualquier recurso: todos lo traen.
    account_id = ""
    region = ""
    for filename, _, _ in INVENTORY:
        items = load(src / filename)
        if items:
            account_id = items[0].get("account_id", "")
            region = items[0].get("region", "")
            break

    graph = GraphBuilder(account, account_id)

    eks = of_type(load(src / "eks.json"), "aws::eks::cluster")
    ec2_count = len(load(src / "ec2.json"))

    body = [
        f"# {account} — Resumen de la cuenta",
        "",
        f"Cuenta AWS `{account_id}`, region principal `{region}`.",
        "",
        "## Que hay en esta cuenta",
        "",
        "| Recurso | Cantidad | Detalle en |",
        "|---|---|---|",
    ]
    for label, count, doc in counts:
        body.append(f"| {label} | {count} | [{doc}]({doc}) |")
    body.append("")

    body += ["## Donde buscar cada cosa", ""]
    if ec2_count:
        body.append(
            "- **Conectividad, firewall, por que A no llega a B** → `compute.md` "
            "(instancias con el catalogo completo de reglas de sus security groups)"
        )
    body += [
        "- **Rutas, VPCs, subnets, salida a internet, conexiones entre cuentas** → `network.md`",
        "- **Bases de datos, buckets, cifrado, exposicion publica** → `data.md`",
        "- **Que aplicaciones corren (Lambda, EKS, balanceadores, colas)** → `workloads.md`",
        "- **Quien puede hacer que (roles, usuarios, claves, secretos)** → `security.md`",
        "",
    ]

    if eks:
        body += [
            "## Nota",
            "",
            f"Esta cuenta tiene {len(eks)} cluster(s) EKS — buena parte de las cargas "
            "corre ahi, no en instancias EC2 directas. Ver `workloads.md`.",
            "",
        ]

    return write_doc(
        dest, "overview.md",
        f"{account} — Resumen de la cuenta",
        account,
        ["aws", "resumen", "indice", account.lower()],
        graph, body,
        category="Resumen de cuenta",
    )
