#!/usr/bin/env python3
"""A/B Experiment Data Quality Audit & Statistical Checks (V2.1).

This script audits Postgres tables `ab_experiment_metadata` and `feedback_events`
to verify:
  1) Deterministic cohort assignment (via SRM check)
  2) Satisfaction difference (A vs B) with significance test (z-approx)

Usage:
  poetry run python scripts/audit_experiment_data.py \
      --dsn postgresql://chimera_user:chimera_secure_password_2024@localhost:5432/chimera_db \
      --expected-a 0.5 --alpha 0.05

Outputs a machine-readable JSON summary and a human-readable report.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from dataclasses import dataclass
from typing import Any

import asyncpg


@dataclass
class SRMResult:
    n_a: int
    n_b: int
    expected_a: float
    chi2: float
    p_value: float
    passed: bool


@dataclass
class SatisfactionResult:
    mean_a: float
    mean_b: float
    diff: float
    se: float
    z: float
    p_value: float
    ci_low: float
    ci_high: float
    passed: bool


def chi_square_gof_two_buckets(n_a: int, n_b: int, p_a: float) -> tuple[float, float]:
    """Chi-square goodness-of-fit for A/B counts, df=1.

    Returns (chi2_stat, p_value). Uses exact df=1 survival via erfc.
    """
    n = n_a + n_b
    if n == 0:
        return 0.0, 1.0
    e_a = n * p_a
    e_b = n * (1 - p_a)
    chi2 = ((n_a - e_a) ** 2) / (e_a + 1e-9) + ((n_b - e_b) ** 2) / (e_b + 1e-9)
    # For df=1, p = erfc(sqrt(chi2/2))
    p = math.erfc(math.sqrt(chi2 / 2.0))
    return chi2, p


def two_sample_z_test(
    mean_a: float, var_a: float, n_a: int, mean_b: float, var_b: float, n_b: int, alpha: float
) -> SatisfactionResult:
    # Welch variance of difference
    se2 = (var_a / max(n_a, 1)) + (var_b / max(n_b, 1))
    se = math.sqrt(max(se2, 1e-12))
    diff = mean_b - mean_a
    z = diff / se if se > 0 else 0.0
    # Normal approx two-sided p-value
    p = 2.0 * 0.5 * math.erfc(abs(z) / math.sqrt(2))
    z_alpha = 1.959963984540054  # ~N(0,1) 97.5% quantile
    ci_low, ci_high = diff - z_alpha * se, diff + z_alpha * se
    passed = (ci_low <= 0 <= ci_high) is False  # True if significant difference
    return SatisfactionResult(
        mean_a=mean_a,
        mean_b=mean_b,
        diff=diff,
        se=se,
        z=z,
        p_value=p,
        ci_low=ci_low,
        ci_high=ci_high,
        passed=passed,
    )


async def fetch_data(conn: asyncpg.Connection) -> dict[str, Any]:
    # SRM counts
    srm_rows = await conn.fetch(
        "SELECT ab_cohort, COUNT(*) AS n FROM ab_experiment_metadata GROUP BY ab_cohort"
    )
    n_a = next((r["n"] for r in srm_rows if r["ab_cohort"] == "A"), 0)
    n_b = next((r["n"] for r in srm_rows if r["ab_cohort"] == "B"), 0)

    # Satisfaction mapping: up=1, down=-1, star=0.5
    sat_rows = await conn.fetch(
        """
        SELECT prompt_variant AS variant,
               AVG(CASE
                     WHEN feedback_type IN ('up','thumbs_up','like') THEN 1.0
                     WHEN feedback_type IN ('down','thumbs_down','dislike') THEN -1.0
                     WHEN feedback_type IN ('star','favorite') THEN 0.5
                     ELSE 0.0
                   END) AS mean,
               VARIANCE(CASE
                     WHEN feedback_type IN ('up','thumbs_up','like') THEN 1.0
                     WHEN feedback_type IN ('down','thumbs_down','dislike') THEN -1.0
                     WHEN feedback_type IN ('star','favorite') THEN 0.5
                     ELSE 0.0
                   END) AS var,
               COUNT(*) AS n
        FROM feedback_events
        WHERE prompt_variant IN ('A','B')
        GROUP BY prompt_variant
        """
    )
    stats = {
        r["variant"]: {"mean": r["mean"] or 0.0, "var": r["var"] or 0.0, "n": r["n"]}
        for r in sat_rows
    }
    return {"n_a": n_a, "n_b": n_b, "stats": stats}


async def main() -> None:
    parser = argparse.ArgumentParser(description="A/B data audit & significance checks")
    parser.add_argument("--dsn", required=True, help="Postgres DSN")
    parser.add_argument("--expected-a", type=float, default=0.5, help="Expected A traffic fraction")
    parser.add_argument("--alpha", type=float, default=0.05, help="Significance level")
    args = parser.parse_args()

    conn = await asyncpg.connect(dsn=args.dsn)
    try:
        data = await fetch_data(conn)
    finally:
        await conn.close()

    n_a, n_b = data["n_a"], data["n_b"]
    chi2, p_srm = chi_square_gof_two_buckets(n_a, n_b, args.expected_a)
    srm_passed = p_srm > args.alpha
    srm = SRMResult(
        n_a=n_a, n_b=n_b, expected_a=args.expected_a, chi2=chi2, p_value=p_srm, passed=srm_passed
    )

    stats = data["stats"]
    a = stats.get("A", {"mean": 0.0, "var": 0.0, "n": 0})
    b = stats.get("B", {"mean": 0.0, "var": 0.0, "n": 0})
    sat = two_sample_z_test(a["mean"], a["var"], a["n"], b["mean"], b["var"], b["n"], args.alpha)

    summary = {
        "srm": srm.__dict__,
        "satisfaction": sat.__dict__,
    }

    print("== A/B Audit Summary ==")
    print(
        f"SRM: nA={n_a}, nB={n_b}, expectedA={args.expected_a:.2f}, chi2={chi2:.3f}, p={p_srm:.4g}, pass={srm_passed}"
    )
    print(
        f"Satisfaction Δ(B-A)={sat.diff:.3f} ± {1.96*sat.se:.3f} (z={sat.z:.2f}, p={sat.p_value:.4g}), pass={sat.passed}"
    )
    print("JSON:")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
