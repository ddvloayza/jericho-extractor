#!/usr/bin/env python3
"""Genera la base de conocimiento en Markdown a partir de la salida de
jericho-extractor.

Por cada cuenta escribe 5 documentos con frontmatter tipado (entidades y
relaciones segun KNOWLEDGE_MODEL.md):

    overview.md    resumen e indice de la cuenta
    compute.md     instancias EC2 + catalogo completo de reglas de SGs
    network.md     VPCs, subnets, ruteo, gateways, conectividad entre cuentas
    data.md        RDS, S3, DynamoDB, EBS, ECR (cifrado y exposicion)
    workloads.md   Lambda, EKS, balanceadores, colas, APIs
    security.md    roles IAM, KMS, secretos, certificados, GuardDuty

A diferencia de knowledge_builder.py, las reglas de los security groups quedan
completas en el documento (protocolo, puertos y origen), con los SGs
referenciados resueltos a nombre y cuenta -- incluso cuando son de otra cuenta.
Eso es lo que permite responder preguntas de conectividad sin volver al JSON.

Uso:
    python build_knowledge.py                          # todas las cuentas
    python build_knowledge.py --account Portal-Prod    # una sola
    python build_knowledge.py --dest ./mi-carpeta      # otro destino
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from knowledge import compute, data, network, overview, security, workloads
from knowledge.common import global_index

DEFAULT_OUTPUT = "output"
DEFAULT_DEST = "knowledge-base"


def build_account(
    account: str,
    src: Path,
    dest: Path,
    sg_index: dict[str, tuple[str, str]],
    kms_index: dict[str, tuple[str, str]],
    vpc_index: dict[str, tuple[str, str]],
) -> list[Path]:
    written: list[Path] = []
    account_dest = dest / account

    for label, result in (
        ("overview", overview.build(account, src, account_dest)),
        ("compute", compute.build(account, src, account_dest, sg_index)),
        ("network", network.build(account, src, account_dest, vpc_index)),
        ("data", data.build(account, src, account_dest, kms_index, sg_index)),
        ("workloads", workloads.build(account, src, account_dest, sg_index)),
        ("security", security.build(account, src, account_dest)),
    ):
        if result is None:
            print(f"  {label:10s} — sin datos, se omite")
            continue
        size_kb = result.stat().st_size / 1024
        print(f"  {label:10s} — {result.name} ({size_kb:.1f} KB)")
        written.append(result)

    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output-dir", default=DEFAULT_OUTPUT,
        help=f"carpeta de salida de jericho-extractor (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--dest", default=DEFAULT_DEST,
        help=f"donde escribir los .md (default: {DEFAULT_DEST})",
    )
    parser.add_argument(
        "--account", action="append", dest="accounts",
        help="procesar solo esta cuenta (se puede repetir). Por defecto, todas.",
    )
    args = parser.parse_args()

    root = Path(args.output_dir).expanduser().resolve()
    if not root.is_dir():
        print(f"No existe la carpeta de salida: {root}", file=sys.stderr)
        return 1

    dest = Path(args.dest).expanduser().resolve()

    available = sorted(
        d.name for d in root.iterdir()
        if d.is_dir() and d.name != "cross_account" and not d.name.startswith(".")
    )
    if not available:
        print(f"No hay carpetas de cuentas en {root}", file=sys.stderr)
        return 1

    accounts = args.accounts or available
    desconocidas = [a for a in accounts if a not in available]
    if desconocidas:
        print(
            f"Cuenta(s) inexistente(s): {', '.join(desconocidas)}\n"
            f"Disponibles: {', '.join(available)}",
            file=sys.stderr,
        )
        return 1

    # Indices globales: se arman una sola vez y se comparten entre cuentas.
    # Son los que permiten resolver una referencia cross-account a nombre y
    # cuenta, en vez de dejar un ID opaco.
    print("Indexando recursos de todas las cuentas (para referencias cross-account)…")
    sg_index = global_index(root, "security_groups.json")
    kms_index = global_index(root, "kms.json")
    vpc_index = global_index(root, "vpcs.json")
    print(f"  {len(sg_index)} security groups, {len(kms_index)} claves KMS, {len(vpc_index)} VPCs\n")

    total = 0
    for account in accounts:
        print(f"{account}")
        total += len(build_account(account, root / account, dest, sg_index, kms_index, vpc_index))
        print()

    print(f"Listo — {total} documentos en {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
