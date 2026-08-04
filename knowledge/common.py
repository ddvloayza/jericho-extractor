"""Utilidades compartidas por los generadores de documentos de conocimiento.

Convierte la salida JSON de jericho-extractor en documentos Markdown con
frontmatter tipado (entidades y relaciones), segun el esquema de
KNOWLEDGE_MODEL.md del repo intelica-brain-plugin.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable

# ── mapeo de relaciones ───────────────────────────────────────────────────────
# El vocabulario de jericho-extractor traducido al esquema fijo de ARCA.
# Una relacion que no este aca se IGNORA en vez de inventarle un tipo nuevo:
# el esquema es curado, extenderlo es una decision humana (editar
# KNOWLEDGE_MODEL.md), no algo que decida un Provider.
RELATION_MAP = {
    "belongs_to_vpc": "IN_VPC",
    "deployed_in_vpc": "IN_VPC",
    "attached_to_vpc": "IN_VPC",
    "deployed_in_subnet": "IN_SUBNET",
    "associated_with_subnet": "IN_SUBNET",
    "uses_subnet": "IN_SUBNET",
    "protected_by_sg": "HAS_SECURITY_GROUP",
    "uses_iam_role": "ASSUMES_ROLE",
    "encrypted_by_kms": "ENCRYPTED_BY",
    "attached_to_instance": "ATTACHED_TO",
    "registered_on_lb": "REGISTERED_ON",
}

# resource_type de jericho -> el valor corto que usamos en el esquema.
RESOURCE_TYPE_MAP = {
    "aws::ec2::instance": "ec2_instance",
    "aws::ec2::security_group": "security_group",
    "aws::ec2::vpc": "vpc",
    "aws::ec2::subnet": "subnet",
    "aws::ec2::volume": "ebs_volume",
    "aws::ec2::route_table": "route_table",
    "aws::ec2::network_acl": "network_acl",
    "aws::ec2::vpc_endpoint": "vpc_endpoint",
    "aws::ec2::nat_gateway": "nat_gateway",
    "aws::ec2::internet_gateway": "internet_gateway",
    "aws::ec2::transit_gateway": "transit_gateway",
    "aws::rds::dbinstance": "rds_instance",
    "aws::s3::bucket": "s3_bucket",
    "aws::lambda::function": "lambda",
    "aws::iam::role": "iam_role",
    "aws::kms::key": "kms_key",
    "aws::secretsmanager::secret": "secret",
    "aws::eks::cluster": "eks_cluster",
    "aws::eks::nodegroup": "eks_nodegroup",
    "aws::elasticloadbalancingv2::loadbalancer": "load_balancer",
    "aws::elasticloadbalancingv2::targetgroup": "target_group",
    "aws::dynamodb::table": "dynamodb_table",
    "aws::sqs::queue": "sqs_queue",
    "aws::sns::topic": "sns_topic",
    "aws::ecr::repository": "ecr_repository",
    "aws::apigateway::restapi": "api_gateway",
}


def load(path: Path) -> list[dict[str, Any]]:
    """Lee un JSON de jericho. Devuelve [] si no existe o no es una lista."""
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def of_type(items: Iterable[dict[str, Any]], *resource_types: str) -> list[dict[str, Any]]:
    """Filtra por resource_type. Varios archivos mezclan tipos (ej. eks.json
    trae clusters y nodegroups juntos)."""
    wanted = set(resource_types)
    return [i for i in items if i.get("resource_type") in wanted]


def name_of(item: dict[str, Any]) -> str:
    """El nombre mas legible disponible: tag Name, resource_name, o el ID."""
    tag_name = (item.get("tags") or {}).get("Name")
    return tag_name or item.get("resource_name") or item.get("resource_id", "")


def tags_line(item: dict[str, Any], skip: tuple[str, ...] = ("Name",)) -> str | None:
    tags = {k: v for k, v in (item.get("tags") or {}).items() if k not in skip}
    if not tags:
        return None
    return "**Tags:** " + ", ".join(f"`{k}={v}`" for k, v in sorted(tags.items()))


# ── indices globales (cross-account) ──────────────────────────────────────────

def global_index(output_root: Path, filename: str) -> dict[str, tuple[str, str]]:
    """Mapa resource_id -> (nombre, cuenta) mirando TODAS las cuentas.

    Hace falta porque los recursos se referencian entre cuentas (peering,
    transit gateway, politicas cross-account). Sin esto una referencia queda
    como un ID opaco que no explica nada.
    """
    index: dict[str, tuple[str, str]] = {}
    if not output_root.is_dir():
        return index
    for account_dir in sorted(output_root.iterdir()):
        if not account_dir.is_dir():
            continue
        for item in load(account_dir / filename):
            index[item["resource_id"]] = (name_of(item), account_dir.name)
    return index


def ref_label(
    resource_id: str,
    index: dict[str, tuple[str, str]],
    account: str,
    kind: str = "",
) -> str:
    """Como se muestra un recurso referenciado. Marca explicitamente cuando es
    de otra cuenta -- eso suele ser la explicacion de una conectividad que si
    no parece salida de la nada."""
    prefix = f"{kind} " if kind else ""
    entry = index.get(resource_id)
    if not entry:
        return f"{prefix}`{resource_id}`"
    name, owner = entry
    if owner != account:
        return f"{prefix}`{resource_id}` ({name} — cuenta **{owner}**)"
    return f"{prefix}`{resource_id}` ({name})" if name else f"{prefix}`{resource_id}`"


# ── construccion de entidades y relaciones ────────────────────────────────────

class GraphBuilder:
    """Acumula entidades y relaciones, deduplicando por ID.

    Deduplicar importa: el mismo SG o la misma VPC aparecen referenciados desde
    muchos recursos, y sin esto el frontmatter se llena de repetidos.
    """

    def __init__(self, account: str, account_id: str = "") -> None:
        self.account = account
        self._entities: dict[str, dict[str, Any]] = {}
        self._relations: list[dict[str, str]] = []
        self._seen_rel: set[tuple[str, str, str]] = set()
        self.entity(
            "Account",
            account,
            **({"account_id": account_id} if account_id else {}),
        )

    def entity(self, entity_type: str, entity_id: str, **props: Any) -> None:
        if not entity_id:
            return
        clean = {k: v for k, v in props.items() if v not in (None, "", [], {})}
        existing = self._entities.get(entity_id)
        if existing:
            # Completa propiedades faltantes sin pisar las que ya estaban: el
            # primer emisor suele tener mas contexto que una referencia suelta.
            for key, value in clean.items():
                existing.setdefault(key, value)
            return
        self._entities[entity_id] = {"type": entity_type, "id": entity_id, **clean}

    def relation(self, source: str, rel_type: str, target: str) -> None:
        if not source or not target or source == target:
            return
        key = (source, rel_type, target)
        if key in self._seen_rel:
            return
        self._seen_rel.add(key)
        self._relations.append({"from": source, "type": rel_type, "to": target})

    def resource(self, item: dict[str, Any], resource_type: str = "", **extra: Any) -> str:
        """Registra un recurso de jericho como entidad `Resource`, con sus
        relaciones declaradas, y lo vincula a la cuenta. Devuelve su ID."""
        rid = item.get("resource_id", "")
        if not rid:
            return ""
        rtype = resource_type or RESOURCE_TYPE_MAP.get(item.get("resource_type", ""), "")
        display = name_of(item)
        self.entity(
            "Resource",
            rid,
            resource_type=rtype,
            name=display if display != rid else None,
            region=item.get("region"),
            **extra,
        )
        self.relation(rid, "BELONGS_TO", self.account)
        for rel in item.get("relationships") or []:
            mapped = RELATION_MAP.get(rel.get("relation", ""))
            if mapped and rel.get("resource_id"):
                self.relation(rid, mapped, rel["resource_id"])
        return rid

    def referenced(self, resource_id: str, resource_type: str, index: dict[str, tuple[str, str]]) -> None:
        """Registra un recurso que solo aparece referenciado (puede ser de otra
        cuenta). Sin esto, las relaciones apuntan a nodos inexistentes."""
        if not resource_id:
            return
        entry = index.get(resource_id)
        self.entity(
            "Resource",
            resource_id,
            resource_type=resource_type,
            name=entry[0] if entry else None,
        )

    def orphans(self) -> list[dict[str, str]]:
        """Relaciones que apuntan a un nodo que no existe. Se usa para validar
        antes de escribir -- un grafo con nodos colgados rompe el traverse."""
        ids = set(self._entities)
        return [r for r in self._relations if r["to"] not in ids]

    @property
    def entities(self) -> list[dict[str, Any]]:
        return list(self._entities.values())

    @property
    def relations(self) -> list[dict[str, str]]:
        return self._relations


# ── escritura del documento ───────────────────────────────────────────────────

def write_doc(
    dest: Path,
    filename: str,
    title: str,
    account: str,
    tags: list[str],
    graph: GraphBuilder,
    body: list[str],
    category: str = "Inventario AWS",
) -> Path:
    """Escribe el documento y, al lado, su fragmento de grafo.

    El grafo va en un archivo hermano (`compute.md` -> `compute.graph.yaml`) en
    vez de dentro del frontmatter. Motivo medido: en un inventario real el
    frontmatter llegaba al 85% del archivo (500+ entidades por cuenta), lo que
    hace que cada lectura del .md gaste tokens en datos que solo le sirven al
    reconstructor del grafo, no a quien lee.

    La trazabilidad se mantiene por convencion de nombre: `X.graph.yaml`
    documenta `X.md`, asi que la relacion DOCUMENTED_IN se deriva sola.
    """
    dest.mkdir(parents=True, exist_ok=True)

    frontmatter = {
        "title": title,
        "account": account,
        # category_raw es el campo que lee scripts/build_index.py del repo de
        # conocimiento para armar la columna Category del INDEX.md.
        "category_raw": category,
        "category_confirmed": True,
        "date": date.today().isoformat(),
        "tags": tags,
        "source": "jericho-extractor",
        "graph": filename.replace(".md", ".graph.yaml"),
    }
    path = dest / filename
    path.write_text(
        "---\n" + to_yaml(frontmatter) + "---\n\n" + "\n".join(body).strip() + "\n",
        encoding="utf-8",
    )

    graph_path = dest / filename.replace(".md", ".graph.yaml")
    graph_path.write_text(
        to_yaml({
            "documents": filename,
            "account": account,
            "entities": graph.entities,
            "relations": graph.relations,
        }),
        encoding="utf-8",
    )
    return path


def to_yaml(data: Any, indent: int = 0) -> str:
    """Serializador YAML minimo, solo para el frontmatter que emitimos aca.
    Evita depender de PyYAML por una estructura de forma conocida."""
    pad = "  " * indent
    out = ""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                out += f"{pad}{key}:\n{to_yaml(value, indent + 1)}"
            else:
                out += f"{pad}{key}: {_scalar(value)}\n"
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                first, *rest = list(item.items())
                out += f"{pad}- {first[0]}: {_scalar(first[1])}\n"
                for key, value in rest:
                    out += f"{pad}  {key}: {_scalar(value)}\n"
            else:
                out += f"{pad}- {_scalar(item)}\n"
    return out


def _scalar(value: Any) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    # Los valores de solo digitos se entrecomillan siempre: en este esquema son
    # identificadores (account_id), nunca cantidades. Sin comillas, un parser
    # YAML los convierte a entero y un ID que empiece con 0 pierde ese cero.
    if text.isdigit():
        return f'"{text}"'
    if text == "" or any(c in text for c in ':#{}[]&*!|>%@`"\'') or text.strip() != text:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text
