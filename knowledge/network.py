"""Documento de red: VPCs, subnets, tablas de ruteo, gateways y toda la
conectividad entre VPCs y cuentas (peerings, transit gateway, endpoints).

Es el complemento de compute.md: ese responde "que permite el firewall", este
responde "existe un camino de red entre estos dos lugares".
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import GraphBuilder, load, name_of, of_type, ref_label, write_doc


def _routes_table(rt: dict[str, Any]) -> list[str]:
    routes = rt.get("routes") or []
    if not routes:
        return ["_Sin rutas._", ""]
    lines = ["| Destino | Target |", "|---|---|"]
    for route in routes:
        dest = (
            route.get("destination_cidr")
            or route.get("destination_ipv6_cidr")
            or route.get("destination_prefix_list_id")
            or "?"
        )
        target = (
            route.get("gateway_id")
            or route.get("nat_gateway_id")
            or route.get("transit_gateway_id")
            or route.get("vpc_peering_connection_id")
            or route.get("network_interface_id")
            or route.get("instance_id")
            or "?"
        )
        state = route.get("state", "")
        suffix = "" if state in ("active", "") else f" _({state})_"
        lines.append(f"| `{dest}` | `{target}`{suffix} |")
    lines.append("")
    return lines


def build(account: str, src: Path, dest: Path, vpc_index: dict[str, tuple[str, str]]) -> Path | None:
    vpcs = load(src / "vpcs.json")
    subnets = load(src / "subnets.json")
    if not vpcs and not subnets:
        return None

    route_tables = load(src / "route_tables.json")
    nat_gws = load(src / "nat_gateways.json")
    igws = load(src / "internet_gateways.json")
    peerings = load(src / "vpc_peerings.json")
    endpoints = load(src / "vpc_endpoints.json")
    tgw_attachments = load(src / "transit_gateway_attachments.json")
    tgws = load(src / "transit_gateways.json")

    account_id = (vpcs or subnets)[0].get("account_id", "")
    region = (vpcs or subnets)[0].get("region", "")
    graph = GraphBuilder(account, account_id)

    for item, rtype in (
        *[(v, "vpc") for v in vpcs],
        *[(s, "subnet") for s in subnets],
        *[(r, "route_table") for r in route_tables],
        *[(n, "nat_gateway") for n in nat_gws],
        *[(i, "internet_gateway") for i in igws],
        *[(e, "vpc_endpoint") for e in endpoints],
        *[(t, "transit_gateway") for t in tgws],
    ):
        graph.resource(item, rtype)

    body = [
        f"# {account} — Red",
        "",
        f"Cuenta `{account_id}`, region `{region}`. "
        f"{len(vpcs)} VPCs, {len(subnets)} subnets, {len(route_tables)} tablas de ruteo.",
        "",
    ]

    # ── VPCs y sus subnets ────────────────────────────────────────────────
    body += ["## VPCs", ""]
    for vpc in sorted(vpcs, key=name_of):
        vid = vpc["resource_id"]
        body += [
            f"### {name_of(vpc)} — `{vid}`",
            "",
            f"- **CIDR:** `{vpc.get('cidr_block', '')}`",
            f"- **Default:** {'si' if vpc.get('is_default') else 'no'}",
            "",
        ]
        own_subnets = [s for s in subnets if s.get("vpc_id") == vid]
        if own_subnets:
            body += ["| Subnet | CIDR | AZ | Publica | IPs libres |", "|---|---|---|---|---|"]
            for sn in sorted(own_subnets, key=lambda s: s.get("availability_zone", "")):
                publica = "si" if sn.get("map_public_ip_on_launch") else "no"
                body.append(
                    f"| {name_of(sn)} `{sn['resource_id']}` "
                    f"| `{sn.get('cidr_block', '')}` "
                    f"| {sn.get('availability_zone', '')} "
                    f"| {publica} "
                    f"| {sn.get('available_ip_count', '?')} |"
                )
            body.append("")

    # ── conectividad entre VPCs / cuentas ─────────────────────────────────
    if peerings or tgw_attachments or tgws:
        body += [
            "## Conectividad entre VPCs y cuentas",
            "",
            "Los caminos de red que existen fuera de esta VPC. Si dos recursos "
            "de cuentas distintas se hablan, tiene que haber una entrada aca "
            "**y** una regla de security group que lo permita.",
            "",
        ]

    # Nota: en el inventario actual no existe ningun VPC peering en ninguna
    # cuenta -- toda la conectividad entre VPCs va por transit gateway. La
    # seccion queda igual por si aparece uno mas adelante.
    if peerings:
        body += ["### VPC peerings", "", "| Peering | Estado |", "|---|---|"]
        for p in peerings:
            body.append(f"| `{p['resource_id']}` | {p.get('status') or p.get('state', '')} |")
        body.append("")

    if tgws:
        body += ["### Transit gateways", ""]
        for t in tgws:
            owner = t.get("owner_id") or t.get("transit_gateway_owner_id") or ""
            body.append(
                f"- `{t['resource_id']}` — {name_of(t)}"
                + (f" (owner `{owner}`)" if owner else "")
            )
        body.append("")

    if tgw_attachments:
        body += [
            "### Attachments a transit gateway",
            "",
            "| Attachment | TGW | Recurso adjunto | Tipo | Estado |",
            "|---|---|---|---|---|",
        ]
        for a in tgw_attachments:
            tgw_owner = a.get("transit_gateway_owner_id", "")
            res_owner = a.get("resource_owner_id", "")
            owner_note = f" (cuenta `{res_owner}`)" if res_owner and res_owner != account_id else ""
            body.append(
                f"| `{a['resource_id']}` "
                f"| `{a.get('transit_gateway_id', '')}`"
                + (f" (cuenta `{tgw_owner}`)" if tgw_owner and tgw_owner != account_id else "")
                + f" | `{a.get('resource_id_ref', '')}`{owner_note} "
                f"| {a.get('attachment_type', '')} "
                f"| {a.get('state', '')} |"
            )
        body.append("")

    # ── gateways de salida ────────────────────────────────────────────────
    if nat_gws or igws:
        body += ["## Salida a internet", ""]
        for igw in igws:
            attached = ", ".join(igw.get("attached_vpc_ids") or []) or "sin adjuntar"
            body.append(f"- **Internet gateway** `{igw['resource_id']}` — VPC: {attached}")
        for nat in nat_gws:
            body.append(
                f"- **NAT gateway** `{nat['resource_id']}` — "
                f"subnet `{nat.get('subnet_id', '')}`, "
                f"IP publica `{nat.get('public_ip', '')}`, estado {nat.get('state', '')}"
            )
        body.append("")

    # ── endpoints ─────────────────────────────────────────────────────────
    if endpoints:
        body += [
            "## VPC endpoints",
            "",
            "Accesos privados a servicios de AWS sin pasar por internet.",
            "",
            "| Endpoint | Servicio | Tipo | VPC |",
            "|---|---|---|---|",
        ]
        for e in sorted(endpoints, key=lambda x: x.get("service_name", "")):
            body.append(
                f"| `{e['resource_id']}` "
                f"| {e.get('service_name', '')} "
                f"| {e.get('endpoint_type', '')} "
                f"| `{e.get('vpc_id', '')}` |"
            )
        body.append("")

    # ── tablas de ruteo ───────────────────────────────────────────────────
    if route_tables:
        body += ["## Tablas de ruteo", ""]
        for rt in sorted(route_tables, key=name_of):
            assoc = rt.get("associated_subnet_ids") or []
            body += [
                f"### {name_of(rt)} — `{rt['resource_id']}`",
                "",
                f"- **VPC:** `{rt.get('vpc_id', '')}`",
                f"- **Principal:** {'si' if rt.get('is_main') else 'no'}",
                f"- **Subnets asociadas:** "
                + (", ".join(f"`{s}`" for s in assoc) if assoc else "ninguna (solo la principal)"),
                "",
            ]
            body += _routes_table(rt)

    return write_doc(
        dest, "network.md",
        f"{account} — Red (VPCs, subnets, ruteo y conectividad)",
        account,
        ["aws", "red", "vpc", "subnet", "ruteo", "peering", account.lower()],
        graph, body,
        category="Red y conectividad",
    )
