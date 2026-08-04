"""Documento de compute: instancias EC2 y el catalogo completo de reglas de
sus security groups.

La diferencia con una tabla de "instancia -> nombres de SG" es que aca estan
las REGLAS: protocolo, puertos y origen, con los SGs referenciados resueltos a
nombre y cuenta. Eso es lo que permite responder "por que la instancia A no
llega a la B" sin salir del archivo.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import GraphBuilder, load, name_of, ref_label, tags_line, write_doc


def fmt_rule(rule: dict[str, Any], sg_index: dict[str, tuple[str, str]], account: str) -> str:
    proto = rule.get("protocol", "")
    proto_label = "todo el trafico" if proto == "-1" else proto

    from_port, to_port = rule.get("from_port"), rule.get("to_port")
    if from_port is None and to_port is None:
        ports = "todos los puertos"
    elif from_port == to_port:
        ports = f"puerto {from_port}"
    else:
        ports = f"puertos {from_port}-{to_port}"

    sources: list[str] = []
    sources += rule.get("ipv4_ranges") or []
    sources += rule.get("ipv6_ranges") or []
    sources += [
        ref_label(gid, sg_index, account, kind="SG")
        for gid in rule.get("referenced_group_ids") or []
    ]
    sources += [f"prefix-list {pid}" for pid in rule.get("prefix_list_ids") or []]

    return f"{proto_label}, {ports} — {', '.join(sources) if sources else 'sin origen definido'}"


def sg_block(
    sg: dict[str, Any],
    sg_index: dict[str, tuple[str, str]],
    account: str,
    used_by: list[str],
) -> list[str]:
    lines = [f"### `{sg['resource_id']}` — {sg.get('group_name') or 'sin nombre'}", ""]
    if sg.get("description"):
        lines += [f"_{sg['description']}_", ""]
    lines += [
        f"**Usado por:** {', '.join(used_by)}" if used_by
        else "**Usado por:** ningun recurso de los listados en este documento — "
             "solo aparece referenciado en reglas de otros SGs "
             "(puede estar en un ALB, RDS o Lambda)",
        "",
    ]

    for label, rules, empty_msg in (
        ("Entrada", sg.get("inbound_rules") or [], "ninguna regla (no acepta trafico entrante)"),
        ("Salida", sg.get("outbound_rules") or [], "ninguna regla"),
    ):
        if rules:
            lines.append(f"**{label}:**")
            lines += [f"- {fmt_rule(r, sg_index, account)}" for r in rules]
        else:
            lines.append(f"**{label}:** {empty_msg}")
        lines.append("")

    return lines


def build(account: str, src: Path, dest: Path, sg_index: dict[str, tuple[str, str]]) -> Path | None:
    ec2 = load(src / "ec2.json")
    if not ec2:
        return None

    sgs = load(src / "security_groups.json")
    subnets = load(src / "subnets.json")
    vpcs = load(src / "vpcs.json")

    sg_by_id = {s["resource_id"]: s for s in sgs}
    subnet_by_id = {s["resource_id"]: s for s in subnets}
    vpc_by_id = {v["resource_id"]: v for v in vpcs}

    account_id = ec2[0].get("account_id", "")
    region = ec2[0].get("region", "")
    graph = GraphBuilder(account, account_id)

    # SGs a documentar: los adjuntos a instancias, mas los referenciados dentro
    # de sus reglas. Sin estos ultimos no se puede seguir la cadena de
    # conectividad ("permite desde el SG X" — y que es X?).
    attached: set[str] = set()
    for inst in ec2:
        attached.update(inst.get("security_group_ids") or [])

    referenced: set[str] = set()
    for sid in attached:
        sg = sg_by_id.get(sid, {})
        for rule in (sg.get("inbound_rules") or []) + (sg.get("outbound_rules") or []):
            referenced.update(rule.get("referenced_group_ids") or [])

    relevant_sgs = attached | referenced

    sg_used_by: dict[str, set[str]] = {sid: set() for sid in relevant_sgs}
    for inst in ec2:
        for sid in inst.get("security_group_ids") or []:
            sg_used_by.setdefault(sid, set()).add(name_of(inst))

    # ── grafo ─────────────────────────────────────────────────────────────
    for inst in ec2:
        graph.resource(
            inst,
            "ec2_instance",
            instance_type=inst.get("instance_type"),
            state=inst.get("state"),
            private_ip=inst.get("private_ip"),
        )

    for sid in sorted(relevant_sgs):
        graph.referenced(sid, "security_group", sg_index)

    for vid in sorted({i.get("vpc_id") for i in ec2 if i.get("vpc_id")}):
        vpc = vpc_by_id.get(vid, {})
        graph.entity("Resource", vid, resource_type="vpc",
                     name=name_of(vpc) if vpc else None, cidr_block=vpc.get("cidr_block"))
        graph.relation(vid, "BELONGS_TO", account)

    for sid in sorted({i.get("subnet_id") for i in ec2 if i.get("subnet_id")}):
        sn = subnet_by_id.get(sid, {})
        graph.entity("Resource", sid, resource_type="subnet",
                     name=name_of(sn) if sn else None,
                     cidr_block=sn.get("cidr_block"),
                     availability_zone=sn.get("availability_zone"))
        if sn.get("vpc_id"):
            graph.relation(sid, "IN_VPC", sn["vpc_id"])

    # ── documento ─────────────────────────────────────────────────────────
    body = [
        f"# {account} — Compute y reglas de red",
        "",
        f"Cuenta `{account_id}`, region `{region}`. "
        f"{len(ec2)} instancias EC2, {len(relevant_sgs)} security groups relevantes.",
        "",
        "Las instancias referencian sus security groups por ID; las reglas "
        "completas estan en el catalogo al final (una sola vez, aunque varias "
        "instancias compartan el mismo SG).",
        "",
        "## Instancias EC2",
        "",
    ]

    for inst in sorted(ec2, key=name_of):
        subnet = subnet_by_id.get(inst.get("subnet_id", ""), {})
        body += [
            f"### {name_of(inst)} — `{inst['resource_id']}`",
            "",
            f"- **Estado:** {inst.get('state', '')}",
            f"- **Tipo:** {inst.get('instance_type', '')} ({inst.get('platform') or 'linux'})",
            f"- **IP privada:** `{inst.get('private_ip', '')}`"
            + (f" — **IP publica:** `{inst['public_ip']}`" if inst.get("public_ip") else ""),
            f"- **VPC:** `{inst.get('vpc_id', '')}`",
            f"- **Subnet:** `{inst.get('subnet_id', '')}`"
            + (f" ({subnet.get('cidr_block')})" if subnet.get("cidr_block") else ""),
            f"- **AZ:** {inst.get('availability_zone', '')}",
        ]
        if inst.get("iam_instance_profile"):
            body.append(f"- **IAM instance profile:** `{inst['iam_instance_profile']}`")

        sg_ids = inst.get("security_group_ids") or []
        body.append(
            "- **Security groups:** "
            + (", ".join(ref_label(s, sg_index, account) for s in sg_ids) if sg_ids else "ninguno")
        )
        tags = tags_line(inst)
        if tags:
            body.append(f"- {tags}")
        body.append("")

    body += [
        "## Catalogo de security groups",
        "",
        "Reglas completas de cada SG. Incluye los adjuntos a instancias y los "
        "que solo aparecen referenciados dentro de otras reglas (necesarios "
        "para seguir la cadena de conectividad de punta a punta).",
        "",
    ]
    for sid in sorted(relevant_sgs, key=lambda s: (sg_by_id.get(s, {}).get("group_name") or s)):
        sg = sg_by_id.get(sid)
        if sg:
            body += sg_block(sg, sg_index, account, sorted(sg_used_by.get(sid, set())))
            continue
        entry = sg_index.get(sid)
        if entry:
            name, owner = entry
            body += [
                f"### `{sid}` — {name}",
                "",
                f"_Pertenece a la cuenta **{owner}**, no a {account}. Aparece aca "
                "porque las reglas de esta cuenta lo referencian (conectividad "
                "cross-account via peering o transit gateway). Sus reglas "
                f"completas estan en el documento de {owner}._",
                "",
            ]
        else:
            body += [
                f"### `{sid}`",
                "",
                "_No esta en ninguna cuenta extraida — puede haber sido borrado, "
                "o pertenecer a una cuenta fuera del alcance del inventario._",
                "",
            ]

    return write_doc(
        dest, "compute.md",
        f"{account} — Compute y reglas de red",
        account,
        ["aws", "ec2", "security-group", "red", "inventario", account.lower()],
        graph, body,
        category="Compute y red",
    )
