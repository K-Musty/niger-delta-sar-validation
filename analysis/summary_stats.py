#!/usr/bin/env python3
"""
Aggregate the pipeline results into paper-ready numbers.
"""
from __future__ import annotations

import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

CAND = config.DATA_INTERIM / "anomaly_candidates.csv"
OBS  = config.DATA_INTERIM / "observability_classes.csv"
DIFF = config.DATA_INTERIM / "per_acquisition_diff.csv"
OUT  = config.DATA_OUTPUT / "stats.json"
OUT.parent.mkdir(parents=True, exist_ok=True)


def main():
    cand = pd.read_csv(CAND)
    obs  = pd.read_csv(OBS)
    diff = pd.read_csv(DIFF)

    # Distance stats
    post_d = cand[~cand["pre_incident"]]["distance_from_reported_m"]
    ctrl_d = cand[cand["pre_incident"]]["distance_from_reported_m"]

    mw = stats.mannwhitneyu(post_d.dropna(), ctrl_d.dropna(),
                            alternative="two-sided")

    # Cluster rate
    n_post_acq = (~diff["pre_incident"]).sum()
    n_ctrl_acq = diff["pre_incident"].sum()
    n_post_clusters = (~cand["pre_incident"]).sum()
    n_ctrl_clusters = cand["pre_incident"].sum()

    summary = {
        "sample_flow": {
            "nosdra_raw_records": 21167,
            "filtered_candidates": 67,
            "incidents_with_sar": 63,
            "acquisitions_extracted": 262,
            "post_incident_diffs": int(n_post_acq),
            "pre_incident_controls": int(n_ctrl_acq),
            "observable_open_water": int(
                (obs["observability"] == "OBSERVABLE_OPEN_WATER").sum()
            ),
            "observable_swamp": int(
                (obs["observability"] == "OBSERVABLE_SWAMP").sum()
            ),
            "distinguishable_spills": 0,
        },
        "cluster_counts": {
            "total": int(len(cand)),
            "post": int(n_post_clusters),
            "control": int(n_ctrl_clusters),
            "post_rate_per_acq": float(n_post_clusters / max(n_post_acq, 1)),
            "control_rate_per_acq": float(n_ctrl_clusters / max(n_ctrl_acq, 1)),
            "rate_ratio": float(
                (n_post_clusters / max(n_post_acq, 1)) /
                (n_ctrl_clusters / max(n_ctrl_acq, 1))
            ),
        },
        "distance_m": {
            "post": {
                "n": int(len(post_d)),
                "median": float(post_d.median()),
                "q25": float(post_d.quantile(0.25)),
                "q75": float(post_d.quantile(0.75)),
            },
            "control": {
                "n": int(len(ctrl_d)),
                "median": float(ctrl_d.median()),
                "q25": float(ctrl_d.quantile(0.25)),
                "q75": float(ctrl_d.quantile(0.75)),
            },
            "mann_whitney_p": float(mw.pvalue),
            "mann_whitney_u": float(mw.statistic),
        },
        "close_clusters_under_500m": {
            "post": int((post_d < 500).sum()),
            "control": int((ctrl_d < 500).sum()),
        },
        "wind_ms": {
            "median": float(
                obs["wind_speed"].median()
            ),
            "q05": float(obs["wind_speed"].quantile(0.05)),
            "q95": float(obs["wind_speed"].quantile(0.95)),
        },
    }

    # Mixed-effects Poisson regression (primary analysis), GLMM + GEE + naive.
    me_path = config.DATA_OUTPUT / "mixed_effects_results.json"
    if me_path.exists():
        with open(me_path) as f:
            summary["mixed_effects"] = json.load(f)

    # Time gap between incident date and first post-incident acquisition.
    tg_path = config.DATA_OUTPUT / "time_gap_stats.json"
    if tg_path.exists():
        with open(tg_path) as f:
            summary["time_gap"] = json.load(f)

    # Sensitivity analysis across contrast / cluster-size grid.
    sens_path = config.DATA_OUTPUT / "sensitivity_analysis.csv"
    if sens_path.exists():
        sens = pd.read_csv(sens_path)
        summary["sensitivity"] = {
            "contrast_levels": sorted(sens["contrast_db"].unique().tolist()),
            "cluster_levels": sorted(sens["min_cluster_px"].unique().tolist()),
            "n_combinations": int(len(sens)),
            "rate_ratio_range": [
                round(float(sens["rate_ratio"].min()), 3),
                round(float(sens["rate_ratio"].max()), 3),
            ],
            "median_dist_post_range_m": [
                round(float(sens["median_dist_post_m"].min()), 0),
                round(float(sens["median_dist_post_m"].max()), 0),
            ],
            "median_dist_ctrl_range_m": [
                round(float(sens["median_dist_ctrl_m"].min()), 0),
                round(float(sens["median_dist_ctrl_m"].max()), 0),
            ],
            "spatial_mismatch_stable_all_p_ns": bool(
                sens["mann_whitney_p"].dropna().gt(0.05).all()
            ),
        }

    with open(OUT, "w") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
