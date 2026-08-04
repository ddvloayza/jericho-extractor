"""Documento de cargas de trabajo: Lambda, EKS y sus workloads de Kubernetes,
balanceadores, colas y APIs.

Es el "que corre aca" de la cuenta, complementando compute.md (que es el "en
que maquina y con que reglas de red").
"""
from __future__ import annotations

from pathlib import Path

from .common import GraphBuilder, load, name_of, of_type, ref_label, write_doc


def build(account: str, src: Path, dest: Path, sg_index: dict[str, tuple[str, str]]) -> Path | None:
    lambdas = load(src / "lambdas.json")
    eks = load(src / "eks.json")
    k8s = load(src / "kubernetes_workloads.json")
    lbs = load(src / "load_balancers.json")
    tgs = load(src / "target_groups.json")
    sqs = load(src / "sqs.json")
    sns = load(src / "sns.json")
    apis = load(src / "api_gateway.json")

    if not any([lambdas, eks, lbs, sqs, sns, apis]):
        return None

    first = (lambdas or eks or lbs or sqs or sns or apis)[0]
    account_id = first.get("account_id", "")
    region = first.get("region", "")
    graph = GraphBuilder(account, account_id)

    clusters = of_type(eks, "aws::eks::cluster")
    nodegroups = of_type(eks, "aws::eks::nodegroup")

    for items, rtype in (
        (lambdas, "lambda"),
        (clusters, "eks_cluster"),
        (nodegroups, "eks_nodegroup"),
        (lbs, "load_balancer"),
        (tgs, "target_group"),
        (sqs, "sqs_queue"),
        (sns, "sns_topic"),
        (apis, "api_gateway"),
    ):
        for item in items:
            graph.resource(item, rtype)

    for sg_id in {s for i in (lambdas + clusters + lbs) for s in (i.get("security_group_ids") or [])}:
        graph.referenced(sg_id, "security_group", sg_index)

    # Los roles de ejecucion se registran aca porque security.md filtra los
    # service-linked de AWS -- sin esto, ASSUMES_ROLE apunta a un nodo vacio.
    for role_arn in {i.get("execution_role") or i.get("role_arn") for i in (lambdas + clusters)}:
        if role_arn:
            graph.entity("Resource", role_arn, resource_type="iam_role",
                         name=role_arn.split("/")[-1])

    for tg in tgs:
        for lb_arn in tg.get("load_balancer_arns") or []:
            graph.relation(tg["resource_id"], "REGISTERED_ON", lb_arn)

    body = [
        f"# {account} — Cargas de trabajo",
        "",
        f"Cuenta `{account_id}`, region `{region}`. "
        f"{len(lambdas)} funciones Lambda, {len(clusters)} clusters EKS, "
        f"{len(lbs)} balanceadores, {len(sqs)} colas SQS, {len(apis)} APIs.",
        "",
    ]

    # ── EKS ───────────────────────────────────────────────────────────────
    if clusters:
        body += ["## Clusters EKS", ""]
        for c in sorted(clusters, key=lambda x: x.get("cluster_name", "")):
            cname = c.get("cluster_name", name_of(c))
            acceso = []
            if c.get("endpoint_public_access"):
                acceso.append("**publico**")
            if c.get("endpoint_private_access"):
                acceso.append("privado")
            body += [
                f"### {cname}",
                "",
                f"- **ARN:** `{c['resource_id']}`",
                f"- **Version de Kubernetes:** {c.get('kubernetes_version', '')}"
                f" — estado {c.get('status', '')}",
                f"- **VPC:** `{c.get('vpc_id', '')}`",
                f"- **Acceso al endpoint:** {', '.join(acceso) or 'no informado'}",
                f"- **Rol:** `{c.get('role_arn', '')}`",
                "",
            ]

            own_ngs = [n for n in nodegroups if cname in n.get("resource_id", "")]
            if own_ngs:
                body += ["**Node groups:**", ""]
                for ng in own_ngs:
                    body.append(
                        f"- `{ng.get('nodegroup_name') or name_of(ng)}` — "
                        f"{', '.join(ng.get('instance_types') or []) or 'tipo no informado'}, "
                        f"desired {ng.get('desired_size', '?')} "
                        f"(min {ng.get('min_size', '?')} / max {ng.get('max_size', '?')})"
                    )
                body.append("")

            deployments = [
                w for w in k8s
                if w.get("resource_type") == "aws::eks::k8s_deployment"
                and w.get("cluster_name") == cname
            ]
            services = [
                w for w in k8s
                if w.get("resource_type") == "aws::eks::k8s_service"
                and w.get("cluster_name") == cname
            ]
            ingresses = [
                w for w in k8s
                if w.get("resource_type") == "aws::eks::k8s_ingress"
                and w.get("cluster_name") == cname
            ]

            if deployments:
                by_ns: dict[str, list[str]] = {}
                for d in deployments:
                    by_ns.setdefault(d.get("namespace", "default"), []).append(name_of(d))
                body += [
                    f"**Workloads:** {len(deployments)} deployments, "
                    f"{len(services)} services, {len(ingresses)} ingresses",
                    "",
                ]
                for ns in sorted(by_ns):
                    if ns in ("kube-system", "kube-public", "kube-node-lease"):
                        continue
                    body.append(f"- `{ns}`: {', '.join(sorted(by_ns[ns]))}")
                body.append("")

    # ── Lambda ────────────────────────────────────────────────────────────
    if lambdas:
        body += [
            "## Funciones Lambda",
            "",
            "| Funcion | Runtime | Memoria | Timeout | En VPC | Rol |",
            "|---|---|---|---|---|---|",
        ]
        for fn in sorted(lambdas, key=name_of):
            en_vpc = f"`{fn['vpc_id']}`" if fn.get("vpc_id") else "**no**"
            role = (fn.get("execution_role") or "").split("/")[-1]
            body.append(
                f"| {name_of(fn)} "
                f"| {fn.get('runtime', '')} "
                f"| {fn.get('memory_mb', '')} MB "
                f"| {fn.get('timeout_seconds', '')}s "
                f"| {en_vpc} "
                f"| `{role}` |"
            )
        body.append("")

        con_sg = [fn for fn in lambdas if fn.get("security_group_ids")]
        if con_sg:
            body += ["**Security groups por funcion:**", ""]
            for fn in sorted(con_sg, key=name_of):
                sgs = ", ".join(
                    ref_label(s, sg_index, account) for s in fn["security_group_ids"]
                )
                body.append(f"- {name_of(fn)}: {sgs}")
            body.append("")

    # ── balanceadores ─────────────────────────────────────────────────────
    if lbs:
        body += ["## Balanceadores de carga", ""]
        for lb in sorted(lbs, key=name_of):
            body += [
                f"### {name_of(lb)}",
                "",
                f"- **Tipo:** {lb.get('lb_type', '')} — esquema "
                + ("**internet-facing**" if lb.get("scheme") == "internet-facing" else f"{lb.get('scheme', '')}"),
                f"- **DNS:** `{lb.get('dns_name', '')}`",
                f"- **VPC:** `{lb.get('vpc_id', '')}` — estado {lb.get('state', '')}",
            ]
            sgs = lb.get("security_group_ids") or []
            if sgs:
                body.append(
                    "- **Security groups:** "
                    + ", ".join(ref_label(s, sg_index, account) for s in sgs)
                )

            own_tgs = [t for t in tgs if lb["resource_id"] in (t.get("load_balancer_arns") or [])]
            if own_tgs:
                body += ["", "**Target groups detras:**", ""]
                for tg in own_tgs:
                    targets = tg.get("targets") or []
                    body.append(
                        f"- `{name_of(tg)}` — {tg.get('protocol', '')}:{tg.get('port', '')}, "
                        f"tipo {tg.get('target_type', '')}, {len(targets)} targets"
                        + (f" — health check `{tg.get('health_check_path')}`"
                           if tg.get("health_check_path") else "")
                    )
            body.append("")

    # ── mensajeria ────────────────────────────────────────────────────────
    if sqs or sns:
        body += ["## Mensajeria", ""]
        if sqs:
            body += ["### Colas SQS", "", "| Cola | FIFO | Mensajes | Cifrado | DLQ |", "|---|---|---|---|---|"]
            for q in sorted(sqs, key=name_of):
                body.append(
                    f"| {name_of(q)} "
                    f"| {'si' if q.get('fifo_queue') else 'no'} "
                    f"| {q.get('approx_messages', 0)} "
                    f"| {'KMS' if q.get('kms_master_key_id') else 'default'} "
                    f"| {'si' if q.get('redrive_policy') else 'no'} |"
                )
            body.append("")
        if sns:
            body += ["### Topicos SNS", ""]
            for t in sorted(sns, key=name_of):
                body.append(
                    f"- `{name_of(t)}` — {t.get('subscription_count', 0)} suscripciones"
                    + (", cifrado con KMS" if t.get("kms_master_key_id") else "")
                )
            body.append("")

    # ── API Gateway ───────────────────────────────────────────────────────
    if apis:
        body += ["## API Gateway", ""]
        for api in sorted(apis, key=name_of):
            body.append(
                f"- `{name_of(api)}` ({api.get('protocol_type', '')}) — "
                f"`{api.get('api_endpoint', '')}`"
            )
        body.append("")

    return write_doc(
        dest, "workloads.md",
        f"{account} — Cargas de trabajo (Lambda, EKS, balanceadores, mensajeria)",
        account,
        ["aws", "lambda", "eks", "kubernetes", "load-balancer", "sqs", account.lower()],
        graph, body,
        category="Cargas de trabajo",
    )
