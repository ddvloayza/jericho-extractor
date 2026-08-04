"""Documento de identidad y seguridad: roles IAM, claves KMS, secretos,
certificados y la configuracion de GuardDuty.

Sobre los roles: hay cientos por cuenta y la enorme mayoria son service-linked
de AWS (creados solos por un servicio, sin interes para una revision). Se
separan de los propios para que la lista sea util.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import GraphBuilder, load, name_of, write_doc

# Roles que AWS crea y gestiona solo. No aportan a una revision de accesos.
SERVICE_LINKED_PREFIX = "/aws-service-role/"


def _is_service_linked(role: dict[str, Any]) -> bool:
    return (role.get("path") or "").startswith(SERVICE_LINKED_PREFIX)


def _policy_names(item: dict[str, Any]) -> str:
    """attached_policies viene como [{"PolicyName": ..., "PolicyArn": ...}]."""
    policies = item.get("attached_policies") or []
    names = [p.get("PolicyName", "") if isinstance(p, dict) else str(p).split("/")[-1]
             for p in policies]
    return ", ".join(n for n in names if n) or "—"


def build(account: str, src: Path, dest: Path) -> Path | None:
    roles = load(src / "iam_roles.json")
    users = load(src / "iam_users.json")
    groups = load(src / "iam_groups.json")
    kms = load(src / "kms.json")
    secrets = load(src / "secrets.json")
    acm = load(src / "acm.json")
    guardduty = load(src / "guardduty.json")

    if not any([roles, users, kms, secrets, acm, guardduty]):
        return None

    first = (roles or users or kms or secrets or acm or guardduty)[0]
    account_id = first.get("account_id", "")
    region = first.get("region", "")
    graph = GraphBuilder(account, account_id)

    own_roles = [r for r in roles if not _is_service_linked(r)]
    service_roles = [r for r in roles if _is_service_linked(r)]

    for item, rtype in (
        *[(r, "iam_role") for r in own_roles],
        *[(k, "kms_key") for k in kms],
        *[(s, "secret") for s in secrets],
    ):
        graph.resource(item, rtype)

    for s in secrets:
        if s.get("kms_key_id"):
            graph.relation(s["resource_id"], "ENCRYPTED_BY", s["kms_key_id"])

    body = [
        f"# {account} — Identidad y seguridad",
        "",
        f"Cuenta `{account_id}`, region `{region}`. "
        f"{len(own_roles)} roles IAM propios ({len(service_roles)} service-linked de AWS, no listados), "
        f"{len(users)} usuarios, {len(kms)} claves KMS, {len(secrets)} secretos.",
        "",
    ]

    # ── roles con confianza externa (lo mas sensible) ─────────────────────
    cross_account = [r for r in own_roles if r.get("trusted_accounts")]
    if cross_account:
        body += [
            "## Roles con confianza cross-account",
            "",
            "Roles que una cuenta externa puede asumir. Es lo primero a revisar "
            "en una auditoria de accesos.",
            "",
            "| Rol | Cuentas que confia |",
            "|---|---|",
        ]
        for r in sorted(cross_account, key=name_of):
            accounts = ", ".join(f"`{a}`" for a in r.get("trusted_accounts") or [])
            body.append(f"| {name_of(r)} | {accounts} |")
        body.append("")

    # ── roles propios ─────────────────────────────────────────────────────
    if own_roles:
        body += [
            "## Roles IAM propios",
            "",
            "| Rol | Servicios que lo asumen | Politicas adjuntas | Politicas inline |",
            "|---|---|---|---|",
        ]
        for r in sorted(own_roles, key=name_of):
            services = ", ".join(r.get("trusted_services") or []) or "—"
            inline = r.get("inline_policy_names") or []
            body.append(
                f"| {name_of(r)} | {services} | {_policy_names(r)} | {len(inline) or '—'} |"
            )
        body.append("")

    # ── usuarios ──────────────────────────────────────────────────────────
    if users:
        body += [
            "## Usuarios IAM",
            "",
            "| Usuario | MFA | Access keys | Grupos | Politicas |",
            "|---|---|---|---|---|",
        ]
        for u in sorted(users, key=name_of):
            keys = u.get("access_keys") or []
            grupos = ", ".join(u.get("groups") or []) or "—"
            body.append(
                f"| `{name_of(u)}` "
                f"| {'si' if u.get('mfa_enabled') else '**no**'} "
                f"| {len(keys) or '—'} "
                f"| {grupos} "
                f"| {_policy_names(u)} |"
            )
        body.append("")

    if groups:
        body += ["## Grupos IAM", ""]
        for g in sorted(groups, key=name_of):
            body.append(f"- `{name_of(g)}`")
        body.append("")

    # ── KMS ───────────────────────────────────────────────────────────────
    if kms:
        propias = [k for k in kms if k.get("key_manager") == "CUSTOMER"]
        body += [
            "## Claves KMS",
            "",
            f"{len(propias)} gestionadas por la cuenta, {len(kms) - len(propias)} por AWS.",
            "",
            "| Clave | Estado | Rotacion | Descripcion |",
            "|---|---|---|---|",
        ]
        for k in sorted(propias or kms, key=name_of):
            body.append(
                f"| `{k.get('key_id', k['resource_id'])}` "
                f"| {k.get('key_state', '')} "
                f"| {'si' if k.get('rotation_enabled') else '**no**'} "
                f"| {k.get('description') or '—'} |"
            )
        body.append("")

    # ── secretos ──────────────────────────────────────────────────────────
    if secrets:
        body += [
            "## Secretos (Secrets Manager)",
            "",
            "| Secreto | Rotacion | Ultimo cambio |",
            "|---|---|---|",
        ]
        for s in sorted(secrets, key=name_of):
            body.append(
                f"| {name_of(s)} "
                f"| {'si' if s.get('rotation_enabled') else 'no'} "
                f"| {(s.get('last_changed_date') or '—')[:10]} |"
            )
        body.append("")

    # ── certificados ──────────────────────────────────────────────────────
    if acm:
        body += ["## Certificados ACM", "", "| Dominio | Estado | Vence |", "|---|---|---|"]
        for c in sorted(acm, key=name_of):
            body.append(
                f"| {c.get('domain_name') or name_of(c)} "
                f"| {c.get('status', '')} "
                f"| {(c.get('not_after') or '—')[:10]} |"
            )
        body.append("")

    # ── GuardDuty ─────────────────────────────────────────────────────────
    if guardduty:
        body += ["## GuardDuty", ""]
        for d in guardduty:
            extras = []
            if d.get("s3_logs_enabled"):
                extras.append("logs S3")
            if d.get("kubernetes_audit_logs_enabled"):
                extras.append("audit logs de Kubernetes")
            if d.get("malware_protection_enabled"):
                extras.append("proteccion contra malware")
            body.append(
                f"- Detector `{d['resource_id']}` — estado **{d.get('status', '')}**, "
                f"frecuencia de publicacion {d.get('finding_publishing_frequency', '')}"
                + (f". Incluye: {', '.join(extras)}" if extras else "")
            )
        body += [
            "",
            "_Esto es la configuracion del detector, no los hallazgos. Los "
            "hallazgos concretos no estan en este inventario._",
            "",
        ]

    return write_doc(
        dest, "security.md",
        f"{account} — Identidad y seguridad (IAM, KMS, secretos, certificados)",
        account,
        ["aws", "seguridad", "iam", "kms", "secretos", "guardduty", account.lower()],
        graph, body,
        category="Identidad y seguridad",
    )
