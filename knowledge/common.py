"""Utilidades compartidas por los generadores de documentos de conocimiento.

Convierte la salida JSON de jericho-extractor en documentos Markdown con
frontmatter tipado (entidades y relaciones), segun el esquema de
KNOWLEDGE_MODEL.md del repo intelica-brain-plugin.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
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

    def carry_over(self, entity: dict[str, Any]) -> None:
        """Inserta una entidad ya armada, tal cual, sin fusionar con nada.

        La usa el arrastre de lapidas: un recurso borrado no se vuelve a
        derivar del inventario (justamente porque ya no esta), asi que entra
        con las propiedades que tenia la ultima vez que se lo vio.
        """
        eid = entity.get("id")
        if eid and eid not in self._entities:
            self._entities[eid] = dict(entity)

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

# ── historial: lapidas y changelog ───────────────────────────────────────────
# El generador es sin estado: lee el JSON crudo y escribe. Sin esto, un recurso
# borrado en AWS simplemente desaparece del repo como si nunca hubiera
# existido, y las relaciones de las conversaciones que lo referenciaban quedan
# colgando. Lo que hay aca compara contra lo que ya estaba escrito en `dest`.

# Si de una corrida a otra se pierde mas de esta fraccion de las entidades
# vivas, se aborta: una extraccion que fallo devuelve listas vacias, y eso es
# indistinguible de "se borro toda la cuenta" salvo por el tamano del salto.
SHRINK_ABORT_RATIO = 0.5
SHRINK_MIN_ENTITIES = 10

# Propiedades que agrega el historial y no vienen del inventario. Se excluyen
# al comparar, o toda lapida figuraria como "modificada" en cada corrida.
_HISTORY_PROPS = ("status", "deleted_detected")


@dataclass
class RunContext:
    """Datos de la corrida que `write_doc` necesita y los 6 generadores no
    tienen. Es estado de modulo a proposito: el script hace una sola pasada,
    de a una cuenta por vez, asi que no hay concurrencia que lo vuelva
    ambiguo, y la alternativa era enhebrar dos parametros por seis firmas que
    no los usan para nada."""

    collected_at: str
    allow_shrink: bool = False
    changes: list[dict[str, Any]] = field(default_factory=list)


_run: RunContext | None = None


def begin_account(collected_at: str, allow_shrink: bool = False) -> RunContext:
    global _run
    _run = RunContext(collected_at=collected_at, allow_shrink=allow_shrink)
    return _run


def collected_date(src: Path) -> str:
    """Fecha real de recoleccion de los datos, no la de hoy.

    Importa porque son cosas distintas y se venian confundiendo: los datos de
    Portal-Prod tenian collected_at 2026-07-12 y el documento decia
    2026-08-02, la fecha en que corrio el script. Tres semanas de diferencia,
    mostrando la mas nueva -- que es la direccion peligrosa.

    Toma la MAS VIEJA de la cuenta: si la extraccion quedo a medias y hay
    archivos de dos corridas, lo honesto es reportar hasta donde llega lo peor.
    """
    preferidos = ("ec2", "vpcs", "security_groups", "subnets", "s3_buckets", "iam_roles")
    candidatos = [src / f"{n}.json" for n in preferidos]
    candidatos += [p for p in sorted(src.glob("*.json")) if p not in candidatos]

    fechas: set[str] = set()
    for path in candidatos:
        for item in load(path)[:1]:
            stamp = item.get("collected_at") if isinstance(item, dict) else None
            if stamp:
                fechas.add(str(stamp)[:10])
    return min(fechas) if fechas else date.today().isoformat()


def read_graph_file(path: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    """Lee un .graph.yaml previo. Solo entiende la forma exacta que emite
    `to_yaml` de este mismo modulo -- no es un parser de YAML general."""
    if not path.exists():
        return {}, []

    entidades: dict[str, dict[str, Any]] = {}
    relaciones: list[dict[str, str]] = []
    seccion: str | None = None
    actual: dict[str, Any] | None = None

    for linea in path.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        if not linea.startswith(" ") and linea.rstrip().endswith(":"):
            seccion = linea.rstrip()[:-1]
            actual = None
            continue
        if not linea.startswith(" "):
            seccion = None
            continue

        item = re.match(r"^\s+-\s+(\w+):\s*(.*)$", linea)
        prop = re.match(r"^\s+(\w+):\s*(.*)$", linea)
        if item:
            actual = {item.group(1): _unquote(item.group(2))}
            if seccion == "entities":
                if actual.get("id"):
                    entidades[actual["id"]] = actual
            elif seccion == "relations":
                relaciones.append(actual)
        elif prop and actual is not None:
            actual[prop.group(1)] = _unquote(prop.group(2))
            # `id` puede venir despues de `type`, asi que se registra al verlo.
            if seccion == "entities" and prop.group(1) == "id":
                entidades[prop.group(2).strip().strip('"')] = actual

    return entidades, relaciones


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _comparable(entity: dict[str, Any]) -> dict[str, Any]:
    return {k: str(v) for k, v in entity.items() if k not in _HISTORY_PROPS}


def apply_history(
    graph: GraphBuilder,
    previas: dict[str, dict[str, Any]],
    relaciones_previas: list[dict[str, str]],
    collected_at: str,
    allow_shrink: bool,
    origen: str,
) -> dict[str, list]:
    """Arrastra como lapidas las entidades que ya no aparecen, y devuelve el
    delta contra la corrida anterior."""
    actuales = {e["id"]: e for e in graph.entities}
    vivas_antes = {i: e for i, e in previas.items() if e.get("status") != "deleted"}

    if (
        not allow_shrink
        and len(vivas_antes) >= SHRINK_MIN_ENTITIES
        and len(actuales) < len(vivas_antes) * SHRINK_ABORT_RATIO
    ):
        raise RuntimeError(
            f"{origen}: las entidades vivas cayeron de {len(vivas_antes)} a "
            f"{len(actuales)}. Una extraccion que fallo devuelve listas vacias y "
            "es indistinguible de un borrado masivo. Este documento NO se "
            "escribio, pero los que se generaron antes que el en esta cuenta si, "
            "asi que quedo a medio regenerar: revisa la extraccion y volve a "
            "correr la cuenta entera. Si el borrado es real, --allow-shrink."
        )

    nuevos, borrados, modificados, reaparecidos = [], [], [], []

    for eid, actual in actuales.items():
        previa = previas.get(eid)
        if previa is None:
            nuevos.append(actual)
        elif previa.get("status") == "deleted":
            reaparecidos.append(actual)
        elif _comparable(previa) != _comparable(actual):
            cambios = {
                k: (previa.get(k), actual.get(k))
                for k in set(_comparable(previa)) | set(_comparable(actual))
                if str(previa.get(k, "")) != str(actual.get(k, ""))
            }
            modificados.append({"entity": actual, "campos": cambios})

    for eid, previa in previas.items():
        if eid in actuales:
            continue
        lapida = dict(previa)
        if previa.get("status") != "deleted":
            # Se detecto ahora. Es "detected" y no "at" a proposito: sabemos
            # cuando dejo de aparecer, no cuando se borro de verdad -- entre
            # dos extracciones pueden pasar semanas.
            lapida["status"] = "deleted"
            lapida["deleted_detected"] = collected_at
            borrados.append(lapida)
        graph.carry_over(lapida)
        for rel in relaciones_previas:
            if rel.get("from") == eid:
                graph.relation(rel["from"], rel.get("type", ""), rel.get("to", ""))

    return {
        "nuevos": nuevos,
        "borrados": borrados,
        "modificados": modificados,
        "reaparecidos": reaparecidos,
    }


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
    graph_path = dest / filename.replace(".md", ".graph.yaml")

    # Antes de pisar: comparar contra lo que ya estaba, arrastrar las lapidas
    # y anotar el delta. Sin RunContext (uso suelto del modulo) se salta todo
    # y se comporta como antes.
    collected_at = _run.collected_at if _run else date.today().isoformat()
    if _run is not None:
        previas, relaciones_previas = read_graph_file(graph_path)
        delta = apply_history(
            graph, previas, relaciones_previas,
            collected_at, _run.allow_shrink, f"{account}/{filename}",
        )
        # Sin estado previo es un bootstrap, no un delta: reportar las 539
        # entidades iniciales como "nuevas" seria ruido, no informacion.
        if previas and any(delta.values()):
            _run.changes.append({"documento": filename, **delta})

    frontmatter = {
        "title": title,
        "account": account,
        # category_raw es el campo que lee scripts/build_index.py del repo de
        # conocimiento para armar la columna Category del INDEX.md.
        "category_raw": category,
        "category_confirmed": True,
        # La fecha de RECOLECCION, no la de hoy: el documento afirma como
        # estaba AWS ese dia, y decir la de generacion lo hace parecer mas
        # fresco de lo que es.
        "date": collected_at,
        "generated": date.today().isoformat(),
        "tags": tags,
        "source": "jericho-extractor",
        "graph": filename.replace(".md", ".graph.yaml"),
    }
    path = dest / filename
    path.write_text(
        "---\n" + to_yaml(frontmatter) + "---\n\n" + "\n".join(body).strip() + "\n",
        encoding="utf-8",
    )

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


def write_changes(dest: Path, account: str, collected_at: str, changes: list[dict]) -> Path | None:
    """Antepone al changelog de la cuenta el delta de esta corrida.

    Va en un documento y no en el grafo a proposito: el grafo modela el estado
    ACTUAL, y un cambio es un evento entre dos estados. Modelarlo como nodos
    haria crecer el grafo sin techo (un SG que cambia por semana son 52 nodos
    al ano); como documento queda acotado, es una sola entrada en el indice, y
    se lee con las tools que ya existen.
    """
    if not changes:
        return None

    lineas = [f"## {collected_at}", ""]
    for doc in changes:
        etiquetas = (
            ("nuevos", "Nuevos"),
            ("reaparecidos", "Reaparecidos"),
            ("borrados", "Borrados"),
            ("modificados", "Modificados"),
        )
        bloques = [(t, doc[k]) for k, t in etiquetas if doc.get(k)]
        if not bloques:
            continue
        lineas.append(f"### {doc['documento']}")
        lineas.append("")
        for titulo, items in bloques:
            lineas.append(f"**{titulo} ({len(items)})**")
            lineas.append("")
            for item in items[:40]:
                if titulo == "Modificados":
                    ent = item["entity"]
                    detalle = ", ".join(
                        f"{k}: {a or '—'} → {b or '—'}" for k, (a, b) in sorted(item["campos"].items())
                    )
                    lineas.append(f"- `{ent['id']}` · {ent.get('resource_type', ent.get('type'))} · {detalle}")
                else:
                    rt = item.get("resource_type", item.get("type", ""))
                    extra = f" · visto por ultima vez {item.get('deleted_detected')}" if titulo == "Borrados" else ""
                    nombre = f" · {item['name']}" if item.get("name") else ""
                    lineas.append(f"- `{item['id']}` · {rt}{nombre}{extra}")
            if len(items) > 40:
                lineas.append(f"- … y {len(items) - 40} mas")
            lineas.append("")

    path = dest / "changes.md"
    previo = ""
    if path.exists():
        texto = path.read_text(encoding="utf-8")
        # Se conserva solo el historial: el frontmatter se reescribe entero
        # para que la fecha del documento sea la de la corrida mas reciente.
        previo = texto.split("\n---\n\n", 1)[-1] if texto.startswith("---") else texto
        previo = previo.split("\n", 2)[-1] if previo.startswith("# ") else previo

    frontmatter = {
        "title": f"{account} — Cambios detectados en el inventario",
        "account": account,
        "category_raw": "Historial de inventario",
        "category_confirmed": True,
        "date": collected_at,
        "generated": date.today().isoformat(),
        "summary": (
            f"Que aparecio, desaparecio y cambio en el inventario de {account} "
            "entre extracciones. Las fechas son de deteccion, no de cuando "
            "ocurrio el cambio en AWS."
        ),
        "tags": ["aws", "inventario", "cambios", "historial", "drift", account.lower()],
        "source": "jericho-extractor",
    }
    encabezado = (
        f"# {account} — Cambios detectados en el inventario\n\n"
        "Cada seccion es una extraccion, la mas reciente arriba. La fecha es "
        "**cuando se detecto** el cambio, no cuando ocurrio en AWS: entre dos "
        "extracciones pueden pasar semanas.\n\n"
    )
    path.write_text(
        "---\n" + to_yaml(frontmatter) + "---\n\n" + encabezado
        + "\n".join(lineas).rstrip() + "\n\n" + previo.strip() + "\n",
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
