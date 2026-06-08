"""
AWS Cost Explorer collector.

Runs 7 queries per account (CE is global — not per region):
  1. Daily by SERVICE                   → costs_daily.json
  2. Daily by SERVICE + TAG:Name        → costs_by_name.json
  3. Daily by SERVICE + USAGE_TYPE      → costs_by_usage.json
  4. Daily by SERVICE + TAG:apid        → costs_by_apid.json
  5. Daily by SERVICE + TAG:assetid     → costs_by_assetid.json
  6. Daily by SERVICE + TAG:env         → costs_by_env.json
  7. Monthly by SERVICE (13 months)     → costs_monthly.json

Requires: ce:GetCostAndUsage permission on the account.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)

DAILY_LOOKBACK_DAYS = 90
MONTHLY_LOOKBACK    = 13   # months including current

# Tags to extract as separate cost dimensions
_TAG_DIMENSIONS = [
    ("Name",     "name"),
    ("apid",     "apid"),
    ("assetid",  "assetid"),
    ("env",      "env"),
]


class CostCollector:
    def __init__(self, ce_client: Any, account_id: str, account_name: str) -> None:
        self.ce           = ce_client
        self.account_id   = account_id
        self.account_name = account_name

    # ── public ────────────────────────────────────────────────────────────────

    def collect(self) -> dict[str, list[dict[str, Any]]]:
        today         = date.today()
        daily_start   = (today - timedelta(days=DAILY_LOOKBACK_DAYS)).isoformat()
        daily_end     = today.isoformat()
        monthly_start = _first_month(today, MONTHLY_LOOKBACK).isoformat()

        results: dict[str, list] = {}

        # ── 1. Daily by service ───────────────────────────────────────────────
        logger.info("[%s] CE — daily by SERVICE (last %d days)",
                    self.account_name, DAILY_LOOKBACK_DAYS)
        results["costs_daily"] = self._query(
            daily_start, daily_end, "DAILY",
            [{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        # ── 2. Daily by SERVICE + USAGE_TYPE ─────────────────────────────────
        logger.info("[%s] CE — daily by SERVICE + USAGE_TYPE", self.account_name)
        results["costs_by_usage"] = self._query(
            daily_start, daily_end, "DAILY",
            [
                {"Type": "DIMENSION", "Key": "SERVICE"},
                {"Type": "DIMENSION", "Key": "USAGE_TYPE"},
            ],
        )

        # ── 3-6. Daily by SERVICE + TAG:<X> for each business tag ─────────────
        for tag_key, result_key in _TAG_DIMENSIONS:
            logger.info("[%s] CE — daily by SERVICE + TAG:%s", self.account_name, tag_key)
            records = self._query(
                daily_start, daily_end, "DAILY",
                [
                    {"Type": "DIMENSION", "Key": "SERVICE"},
                    {"Type": "TAG",       "Key": tag_key},
                ],
                tag_field=result_key,
            )
            results[f"costs_by_{result_key}"] = records

        # ── 7. Monthly by service (13 months) ────────────────────────────────
        logger.info("[%s] CE — monthly last %d months", self.account_name, MONTHLY_LOOKBACK)
        results["costs_monthly"] = self._query(
            monthly_start, daily_end, "MONTHLY",
            [{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        # Summary
        this_month = today.strftime("%Y-%m")
        total = sum(
            r["amount"] for r in results["costs_daily"]
            if r.get("date", "").startswith(this_month)
        )
        logger.info("[%s] CE done — %s total so far: $%.2f",
                    self.account_name, this_month, total)
        return results

    # ── internals ─────────────────────────────────────────────────────────────

    def _query(
        self,
        start:      str,
        end:        str,
        granularity: str,
        group_by:   list[dict],
        tag_field:  str = "name",   # field name for TAG type groups
    ) -> list[dict[str, Any]]:
        records:    list[dict] = []
        next_token: str | None = None

        while True:
            kwargs: dict[str, Any] = {
                "TimePeriod":  {"Start": start, "End": end},
                "Granularity": granularity,
                "Metrics":     ["BlendedCost"],
                "GroupBy":     group_by,
            }
            if next_token:
                kwargs["NextPageToken"] = next_token

            try:
                resp = self.ce.get_cost_and_usage(**kwargs)
            except Exception as exc:
                logger.warning("[%s] CE query failed: %s", self.account_name, exc)
                return records

            for period in resp.get("ResultsByTime", []):
                date_str = period["TimePeriod"]["Start"]
                for group in period.get("Groups", []):
                    keys   = group["Keys"]
                    amount = float(group["Metrics"]["BlendedCost"]["Amount"])
                    if amount == 0.0:
                        continue

                    record: dict[str, Any] = {
                        "date":         date_str,
                        "amount":       round(amount, 6),
                        "unit":         group["Metrics"]["BlendedCost"]["Unit"],
                        "account_id":   self.account_id,
                        "account_name": self.account_name,
                    }
                    for i, g in enumerate(group_by):
                        field = tag_field if g["Type"] == "TAG" else _dim_field(g["Key"])
                        value = keys[i] if i < len(keys) else ""
                        # CE returns TAG values as "TagKey$TagValue" — strip the prefix
                        if g["Type"] == "TAG" and "$" in value:
                            value = value.split("$", 1)[1]
                        record[field] = value

                    records.append(record)

            next_token = resp.get("NextPageToken")
            if not next_token:
                break

        return records


# ── helpers ───────────────────────────────────────────────────────────────────

def _dim_field(key: str) -> str:
    return {
        "SERVICE":       "service",
        "USAGE_TYPE":    "usage_type",
        "REGION":        "region",
        "INSTANCE_TYPE": "instance_type",
        "OPERATION":     "operation",
        "LINKED_ACCOUNT":"linked_account",
    }.get(key, key.lower())


def _first_month(today: date, lookback_months: int) -> date:
    """Return the first day of the month `lookback_months` ago."""
    month = today.month - lookback_months
    year  = today.year
    while month <= 0:
        month += 12
        year  -= 1
    return date(year, month, 1)
