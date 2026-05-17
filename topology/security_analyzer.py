from __future__ import annotations

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

PUBLIC_CIDRS = frozenset({"0.0.0.0/0", "::/0"})


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"
    INFO     = "info"


_RISK_ORDER = [RiskLevel.CRITICAL, RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW, RiskLevel.INFO]


def _max_risk(levels: list[RiskLevel]) -> RiskLevel:
    for lvl in _RISK_ORDER:
        if lvl in levels:
            return lvl
    return RiskLevel.INFO


class SecurityAnalyzer:
    """Analyzes security groups and classifies exposure risk.

    Input: normalized security_group dicts from SecurityGroupCollector.
    Output: enriched analysis dicts with risk classifications per rule.
    """

    def analyze_all(
        self,
        security_groups: list[dict[str, Any]],
        all_resources: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        # Build index: sg_id → list of resource_ids that use it
        sg_to_resources: dict[str, list[str]] = {}
        for resource in all_resources:
            for sg_id in resource.get("security_group_ids", []):
                sg_to_resources.setdefault(sg_id, []).append(resource["resource_id"])

        results = []
        for sg in security_groups:
            results.append(self.analyze_sg(sg, sg_to_resources.get(sg["resource_id"], [])))
        logger.info("SecurityAnalyzer: analyzed %d security groups", len(results))
        return results

    def analyze_sg(
        self,
        sg: dict[str, Any],
        attached_resources: list[str],
    ) -> dict[str, Any]:
        inbound  = [self._analyze_rule(r, "inbound")  for r in sg.get("inbound_rules", [])]
        outbound = [self._analyze_rule(r, "outbound") for r in sg.get("outbound_rules", [])]

        all_risk_levels = [r["risk_level"] for r in inbound + outbound]
        overall_risk = _max_risk(all_risk_levels)

        flags: set[str] = set()
        for r in inbound + outbound:
            flags.update(r["risk_tags"])

        return {
            "security_group_id":   sg["resource_id"],
            "security_group_name": sg.get("group_name", ""),
            "description":         sg.get("description", ""),
            "vpc_id":              sg.get("vpc_id", ""),
            "account_id":          sg.get("account_id", ""),
            "region":              sg.get("region", ""),
            "attached_resources":  attached_resources,
            "attached_count":      len(attached_resources),
            "overall_risk":        overall_risk,
            "exposure_flags":      sorted(flags),
            "inbound_rule_count":  len(inbound),
            "outbound_rule_count": len(outbound),
            "inbound_analysis":    inbound,
            "outbound_analysis":   outbound,
        }

    # ── Rule analysis ─────────────────────────────────────────────────────────

    def _analyze_rule(self, rule: dict[str, Any], direction: str) -> dict[str, Any]:
        protocol   = rule.get("protocol", "-1") or "-1"
        from_port  = rule.get("from_port")   # can be None
        to_port    = rule.get("to_port")     # can be None

        # Collect all CIDRs from this rule
        cidrs = [c for c in rule.get("ipv4_ranges", []) if c] + \
                [c for c in rule.get("ipv6_ranges", []) if c]
        ref_sgs = [r for r in rule.get("referenced_group_ids", []) if r]

        risk_tags: list[str] = []
        risk_level = RiskLevel.INFO
        is_public  = any(c in PUBLIC_CIDRS for c in cidrs)

        if ref_sgs:
            risk_tags.append("sg_reference")

        if is_public:
            if direction == "inbound":
                risk_level, risk_tags = self._classify_inbound(protocol, from_port, to_port, risk_tags)
            else:
                risk_tags.append("unrestricted_egress")
                risk_level = RiskLevel.LOW
        elif cidrs and not ref_sgs:
            risk_tags.append("internal_only")
            risk_level = RiskLevel.INFO

        return {
            "protocol":     protocol,
            "from_port":    from_port,
            "to_port":      to_port,
            "cidrs":        cidrs,
            "referenced_sgs": ref_sgs,
            "is_public":    is_public,
            "direction":    direction,
            "risk_level":   risk_level,
            "risk_tags":    risk_tags,
        }

    @staticmethod
    def _classify_inbound(
        protocol: str,
        from_port: int | None,
        to_port: int | None,
        existing_tags: list[str],
    ) -> tuple[RiskLevel, list[str]]:
        tags = list(existing_tags)
        fp = from_port if from_port is not None else -1
        tp = to_port   if to_port   is not None else 65535

        if protocol == "-1":
            tags.append("full_open_inbound")
            return RiskLevel.CRITICAL, tags
        if protocol == "tcp":
            if fp <= 22 <= tp:
                tags.append("ssh_public")
                return RiskLevel.CRITICAL, tags
            if fp <= 3389 <= tp:
                tags.append("rdp_public")
                return RiskLevel.CRITICAL, tags
            if fp <= 5985 <= tp or fp <= 5986 <= tp:
                tags.append("winrm_public")
                return RiskLevel.CRITICAL, tags
            if fp <= 80 <= tp:
                tags.append("http_public")
                return RiskLevel.HIGH, tags
            if fp <= 443 <= tp:
                tags.append("https_public")
                return RiskLevel.MEDIUM, tags
            if fp <= 8080 <= tp or fp <= 8443 <= tp:
                tags.append("alt_http_public")
                return RiskLevel.MEDIUM, tags
        if protocol in ("tcp", "udp", "-1") and fp == 0 and tp == 65535:
            tags.append("all_ports_public")
            return RiskLevel.HIGH, tags

        tags.append("public_port")
        return RiskLevel.MEDIUM, tags


# ── Convenience: summary of critical findings ─────────────────────────────────

def critical_findings(analyses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only SGs with CRITICAL or HIGH overall risk, sorted by risk."""
    order = {RiskLevel.CRITICAL: 0, RiskLevel.HIGH: 1}
    findings = [a for a in analyses if a["overall_risk"] in (RiskLevel.CRITICAL, RiskLevel.HIGH)]
    return sorted(findings, key=lambda a: order.get(a["overall_risk"], 99))


def public_exposure_summary(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    """High-level counts by exposure flag."""
    flag_counts: dict[str, int] = {}
    for a in analyses:
        for flag in a["exposure_flags"]:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1
    return {
        "total_sgs":           len(analyses),
        "critical_sgs":        sum(1 for a in analyses if a["overall_risk"] == RiskLevel.CRITICAL),
        "high_sgs":            sum(1 for a in analyses if a["overall_risk"] == RiskLevel.HIGH),
        "sgs_with_attached":   sum(1 for a in analyses if a["attached_count"] > 0),
        "flag_counts":         flag_counts,
    }
