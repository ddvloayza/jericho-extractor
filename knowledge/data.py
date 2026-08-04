"""Documento de datos: RDS, S3, DynamoDB, volumenes EBS y ECR.

Resalta lo que suele importar en una revision: que esta cifrado, que es
publicamente accesible, y con que clave KMS.
"""
from __future__ import annotations

from pathlib import Path

from .common import GraphBuilder, load, name_of, ref_label, tags_line, write_doc


def build(
    account: str,
    src: Path,
    dest: Path,
    kms_index: dict[str, tuple[str, str]],
    sg_index: dict[str, tuple[str, str]],
) -> Path | None:
    rds = load(src / "rds.json")
    buckets = load(src / "s3_buckets.json")
    dynamodb = load(src / "dynamodb.json")
    volumes = load(src / "ebs.json")
    ecr = load(src / "ecr.json")

    if not any([rds, buckets, dynamodb, volumes, ecr]):
        return None

    first = (rds or buckets or dynamodb or volumes or ecr)[0]
    account_id = first.get("account_id", "")
    region = first.get("region", "")
    graph = GraphBuilder(account, account_id)

    for items, rtype in (
        (rds, "rds_instance"),
        (buckets, "s3_bucket"),
        (dynamodb, "dynamodb_table"),
        (volumes, "ebs_volume"),
        (ecr, "ecr_repository"),
    ):
        for item in items:
            graph.resource(item, rtype)
            key = item.get("kms_key_id") or item.get("kms_key_arn")
            if key:
                graph.referenced(key, "kms_key", kms_index)
                graph.relation(item["resource_id"], "ENCRYPTED_BY", key)
            # Los SGs referenciados (RDS los tiene) se registran para que la
            # relacion HAS_SECURITY_GROUP no quede apuntando a un nodo vacio.
            for sg_id in item.get("security_group_ids") or []:
                graph.referenced(sg_id, "security_group", sg_index)

    body = [
        f"# {account} — Datos",
        "",
        f"Cuenta `{account_id}`, region `{region}`. "
        f"{len(rds)} RDS, {len(buckets)} buckets S3, {len(dynamodb)} tablas DynamoDB, "
        f"{len(volumes)} volumenes EBS, {len(ecr)} repos ECR.",
        "",
    ]

    # ── RDS ───────────────────────────────────────────────────────────────
    if rds:
        body += ["## Bases de datos RDS", ""]
        for db in sorted(rds, key=name_of):
            sg_ids = db.get("security_group_ids") or []
            body += [
                f"### {name_of(db)} — `{db['resource_id']}`",
                "",
                f"- **Motor:** {db.get('engine', '')} {db.get('engine_version', '')}",
                f"- **Clase:** {db.get('instance_class', '')} — "
                f"{db.get('allocated_storage_gb', '?')} GB — estado {db.get('status', '')}",
                f"- **Endpoint:** `{db.get('endpoint_address', '')}:{db.get('endpoint_port', '')}`",
                f"- **VPC:** `{db.get('vpc_id', '')}` — subnet group `{db.get('subnet_group_name', '')}`",
                f"- **Multi-AZ:** {'si' if db.get('multi_az') else 'no'}"
                f" — AZ `{db.get('availability_zone', '')}`"
                + (f" / secundaria `{db['secondary_az']}`" if db.get("secondary_az") else ""),
                f"- **Accesible publicamente:** "
                + ("**SI**" if db.get("publicly_accessible") else "no"),
                f"- **Cifrado:** "
                + (f"si — KMS `{db.get('kms_key_id', '')}`" if db.get("storage_encrypted") else "**NO**"),
                f"- **Backups:** {db.get('backup_retention_days', 0)} dias de retencion"
                f" — proteccion de borrado: {'si' if db.get('deletion_protection') else '**no**'}",
                "- **Security groups:** "
                + (", ".join(f"`{s}`" for s in sg_ids) if sg_ids else "ninguno"),
                "",
            ]

    # ── S3 ────────────────────────────────────────────────────────────────
    if buckets:
        body += [
            "## Buckets S3",
            "",
            "| Bucket | Cifrado | Versionado | Acceso publico bloqueado | Logs |",
            "|---|---|---|---|---|",
        ]
        for b in sorted(buckets, key=name_of):
            blocked = all([
                b.get("block_public_acls"),
                b.get("ignore_public_acls"),
                b.get("block_public_policy"),
                b.get("restrict_public_buckets"),
            ])
            publico = "" if blocked else " ⚠️"
            body.append(
                f"| `{name_of(b)}` "
                f"| {b.get('encryption_type') or '**ninguno**'} "
                f"| {b.get('versioning_status') or 'no'} "
                f"| {'si' if blocked else '**parcial o no**'}{publico} "
                f"| {'si' if b.get('logging_enabled') else 'no'} |"
            )
        body.append("")

        expuestos = [b for b in buckets if b.get("acl_public") or b.get("bucket_policy_public")]
        if expuestos:
            body += [
                "**Buckets con ACL o policy publica:**",
                "",
                *[f"- `{name_of(b)}`" for b in sorted(expuestos, key=name_of)],
                "",
            ]

    # ── DynamoDB ──────────────────────────────────────────────────────────
    if dynamodb:
        body += ["## Tablas DynamoDB", ""]
        for t in sorted(dynamodb, key=name_of):
            body.append(
                f"- `{name_of(t)}` — estado {t.get('status', '?')}"
                + (f", {t.get('item_count')} items" if t.get("item_count") is not None else "")
                + f", cifrado en reposo: {'si' if t.get('sse_enabled') else 'default de AWS'}"
                + (f", billing {t.get('billing_mode')}" if t.get("billing_mode") else "")
            )
        body.append("")

    # ── EBS ───────────────────────────────────────────────────────────────
    if volumes:
        sin_cifrar = [v for v in volumes if not v.get("encrypted")]
        body += [
            "## Volumenes EBS",
            "",
            f"{len(volumes)} volumenes"
            + (f", **{len(sin_cifrar)} sin cifrar**." if sin_cifrar else ", todos cifrados."),
            "",
        ]
        if sin_cifrar:
            body += ["| Volumen | Tamaño | Tipo | Adjunto a |", "|---|---|---|---|"]
            for v in sorted(sin_cifrar, key=name_of):
                attached = ", ".join(f"`{i}`" for i in (v.get("attached_instances") or []))
                body.append(
                    f"| `{v['resource_id']}` ({name_of(v)}) "
                    f"| {v.get('size_gb', '?')} GB "
                    f"| {v.get('volume_type', '')} "
                    f"| {attached or 'sin adjuntar'} |"
                )
            body.append("")

    # ── ECR ───────────────────────────────────────────────────────────────
    if ecr:
        body += ["## Repositorios ECR", ""]
        for r in sorted(ecr, key=name_of):
            body.append(
                f"- `{name_of(r)}`"
                + (f" — scan on push: {'si' if r.get('scan_on_push') else 'no'}"
                   if "scan_on_push" in r else "")
                + (f", mutabilidad: {r.get('image_tag_mutability')}"
                   if r.get("image_tag_mutability") else "")
            )
        body.append("")

    return write_doc(
        dest, "data.md",
        f"{account} — Datos (RDS, S3, DynamoDB, EBS, ECR)",
        account,
        ["aws", "datos", "rds", "s3", "dynamodb", "cifrado", account.lower()],
        graph, body,
        category="Datos y almacenamiento",
    )
