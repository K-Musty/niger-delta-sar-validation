#!/usr/bin/env python3
"""
Mixed-effects Poisson regression to address pseudoreplication.

Clusters are nested within acquisitions, which are nested within incidents.
A naive Poisson rate test treats every acquisition as independent and
overstates precision. This script fits three models on the same
acquisition-level dataset:

  1. PRIMARY   - Poisson GLMM with a random intercept per incident
                 (statsmodels PoissonBayesMixedGLM, Laplace / MAP).
  2. SECONDARY - Poisson GEE with exchangeable working correlation
                 (population-averaged; a robustness check).
  3. REFERENCE - naive Poisson rate ratio (the V1 primary, kept for
                 comparison).

All results are reported as incidence rate ratios (IRR) with 95% CIs.
"""
from __future__ import annotations

import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

CAND_CSV = config.DATA_INTERIM / "anomaly_candidates.csv"
OBS_CSV  = config.DATA_INTERIM / "observability_classes.csv"
DIFF_CSV = config.DATA_INTERIM / "per_acquisition_diff.csv"
OUT_JSON = config.DATA_OUTPUT / "mixed_effects_results.json"


def build_acq_level_data():
    """Build an acquisition-level dataset with cluster counts."""
    cand = pd.read_csv(CAND_CSV)
    diff = pd.read_csv(DIFF_CSV)
    obs  = pd.read_csv(OBS_CSV)

    diff = diff.merge(
        obs[["incident_id", "sar_date", "observability", "habitat_group"]],
        left_on=["incident_id", "target_date"],
        right_on=["incident_id", "sar_date"],
        how="left",
    )
    diff["observability"] = diff["observability"].fillna("UNKNOWN_HABITAT")
    diff["habitat_group"] = diff["habitat_group"].fillna("unknown")

    cluster_counts = (
        cand.groupby(["incident_id", "target_date", "pre_incident"])
        .size()
        .reset_index(name="n_clusters")
    )

    acq = diff.merge(
        cluster_counts,
        on=["incident_id", "target_date", "pre_incident"],
        how="left",
    )
    acq["n_clusters"] = acq["n_clusters"].fillna(0).astype(int)
    acq["post"] = (~acq["pre_incident"]).astype(int)
    return acq


def _irr_ci(coef, se):
    """Convert a log-scale coefficient and SE to IRR and a 95% CI."""
    return (
        float(np.exp(coef)),
        float(np.exp(coef - 1.96 * se)),
        float(np.exp(coef + 1.96 * se)),
    )


def fit_glmm(df, label="All QC-passing"):
    """Primary: Poisson GLMM with a random intercept per incident."""
    from statsmodels.genmod.bayes_mixed_glm import PoissonBayesMixedGLM

    d = df[["incident_id", "post", "n_clusters"]].dropna().copy()
    d = d.sort_values("incident_id").reset_index(drop=True)
    d["incident_id"] = d["incident_id"].astype(str)

    if d["incident_id"].nunique() < 3 or len(d) < 5:
        return None

    model = PoissonBayesMixedGLM.from_formula(
        "n_clusters ~ post",
        {"incident": "0 + C(incident_id)"},
        d,
    )
    try:
        res = model.fit_map()
    except Exception as e:
        print(f"  [{label}] GLMM fit failed: {e}")
        return None

    # Fixed effects: [intercept, post]
    fe_mean = np.asarray(res.fe_mean).ravel()
    fe_sd = np.asarray(res.fe_sd).ravel()
    coef = float(fe_mean[1])
    se = float(fe_sd[1])
    irr, lo, hi = _irr_ci(coef, se)
    p = float(2 * sp_stats.norm.sf(abs(coef / se)))

    n_post = int((d["post"] == 1).sum())
    n_ctrl = int((d["post"] == 0).sum())
    n_inc = int(d["incident_id"].nunique())

    print(f"\n  [{label}] GLMM (random intercept per incident)")
    print(f"    N acquisitions: {len(d)} ({n_post} post, {n_ctrl} control)")
    print(f"    N incidents:    {n_inc}")
    print(f"    IRR = {irr:.3f} [95% CI {lo:.3f}, {hi:.3f}], p = {p:.4f}")
    print(f"    log-IRR coef = {coef:.4f} (SD {se:.4f})")

    return {
        "model": "GLMM",
        "n_acquisitions": int(len(d)),
        "n_post": n_post,
        "n_control": n_ctrl,
        "n_incidents": n_inc,
        "IRR": round(irr, 3),
        "IRR_CI_lower": round(lo, 3),
        "IRR_CI_upper": round(hi, 3),
        "p_value": round(p, 4),
        "coefficient": round(coef, 4),
        "std_error": round(se, 4),
    }


def fit_gee(df, label="All QC-passing"):
    """Secondary: Poisson GEE with exchangeable correlation."""
    from statsmodels.genmod.generalized_estimating_equations import GEE
    from statsmodels.genmod.families import Poisson
    from statsmodels.genmod.cov_struct import Exchangeable

    d = df[["incident_id", "post", "n_clusters"]].dropna().copy()
    d = d.sort_values("incident_id").reset_index(drop=True)

    if d["incident_id"].nunique() < 3 or len(d) < 5:
        return None

    model = GEE.from_formula(
        "n_clusters ~ post",
        groups="incident_id",
        data=d,
        family=Poisson(),
        cov_struct=Exchangeable(),
    )
    try:
        res = model.fit()
    except Exception as e:
        print(f"  [{label}] GEE fit failed: {e}")
        return None

    coef = float(res.params["post"])
    se = float(res.bse["post"])
    p = float(res.pvalues["post"])
    irr, lo, hi = _irr_ci(coef, se)

    print(f"  [{label}] GEE (exchangeable): "
          f"IRR = {irr:.3f} [{lo:.3f}, {hi:.3f}], p = {p:.4f}")

    return {
        "gee_irr": round(irr, 3),
        "gee_ci_lower": round(lo, 3),
        "gee_ci_upper": round(hi, 3),
        "gee_p": round(p, 4),
        "gee_coefficient": round(coef, 4),
        "gee_std_error": round(se, 4),
    }


def naive_poisson_comparison(df, label="All QC-passing"):
    """Reference: naive Poisson rate ratio (V1 primary)."""
    post = df[df["post"] == 1]
    ctrl = df[df["post"] == 0]

    n_post_acq = len(post)
    n_ctrl_acq = len(ctrl)
    n_post_clusters = int(post["n_clusters"].sum())
    n_ctrl_clusters = int(ctrl["n_clusters"].sum())

    post_rate = n_post_clusters / max(n_post_acq, 1)
    ctrl_rate = n_ctrl_clusters / max(n_ctrl_acq, 1)
    ratio = post_rate / ctrl_rate if ctrl_rate > 0 else float("nan")

    print(f"  [{label}] Naive rate ratio: {ratio:.3f} "
          f"({n_post_clusters}/{n_post_acq} vs "
          f"{n_ctrl_clusters}/{n_ctrl_acq})")

    return {
        "naive_rate_ratio": round(float(ratio), 3),
        "post_clusters": n_post_clusters,
        "ctrl_clusters": n_ctrl_clusters,
        "post_acquisitions": n_post_acq,
        "ctrl_acquisitions": n_ctrl_acq,
    }


def main():
    print("=" * 66)
    print("MIXED-EFFECTS POISSON REGRESSION")
    print("GLMM (random intercept) = primary; GEE = robustness")
    print("=" * 66)

    acq = build_acq_level_data()

    strata = {
        "All QC-passing": acq,
        "Observable (OW+Swamp)": acq[acq["observability"].isin([
            "OBSERVABLE_OPEN_WATER", "OBSERVABLE_SWAMP"])],
        "Open water only": acq[acq["observability"] == "OBSERVABLE_OPEN_WATER"],
        "Terrestrial": acq[acq["observability"] == "UNOBSERVABLE_TERRESTRIAL"],
        "Other (low wind/rain/unknown)": acq[acq["observability"].isin([
            "UNOBSERVABLE_LOW_WIND", "UNOBSERVABLE_RAIN", "UNKNOWN_HABITAT"])],
    }

    results = {}
    for label, subset in strata.items():
        if len(subset) < 5:
            print(f"\n  [{label}] Skipped — too few observations ({len(subset)})")
            continue

        naive = naive_poisson_comparison(subset.copy(), label)
        gee = fit_gee(subset.copy(), label) or {}
        glmm = fit_glmm(subset.copy(), label) or {}

        entry = {"stratum": label}
        entry.update(naive)
        entry.update(gee)
        if glmm:
            entry.update(glmm)
        elif gee:
            entry["model"] = "GEE"
        else:
            entry["model"] = "naive"
        results[label] = entry

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'=' * 66}")
    print(f"Results saved to {OUT_JSON}")
    print(f"{'=' * 66}")

    hdr = f"{'Stratum':<30}{'IRR':>7}{'95% CI':>20}{'p':>8}{'Naive':>8}"
    print("\n" + hdr)
    print("-" * len(hdr))
    for label, r in results.items():
        irr = r.get("IRR")
        if irr is None:
            print(f"{label:<30}  (GLMM failed; model={r['model']})")
            continue
        print(f"{label:<30}{irr:>7.3f}"
              f"[{r['IRR_CI_lower']:.3f}–{r['IRR_CI_upper']:.3f}]"
              f"{r['p_value']:>8.4f}{r['naive_rate_ratio']:>8.3f}")


if __name__ == "__main__":
    main()
