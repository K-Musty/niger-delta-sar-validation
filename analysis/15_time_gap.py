#!/usr/bin/env python3
"""
Compute the distribution of time gaps between NOSDRA incident dates
and the first post-incident Sentinel-1 acquisition.

Reports descriptive statistics for inclusion in Section 4.1 of the paper.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

DIFF_CSV = config.DATA_INTERIM / "per_acquisition_diff.csv"
CAND_CSV = config.DATA_INTERIM / "candidates_flagged.csv"
OUT_JSON = config.DATA_OUTPUT / "time_gap_stats.json"


def main():
    diff = pd.read_csv(DIFF_CSV)
    cand = pd.read_csv(CAND_CSV)

    # Get incident dates
    incident_dates = cand.set_index("incident_id")["date"].to_dict()

    # Filter to post-incident acquisitions only
    post = diff[~diff["pre_incident"]].copy()
    post["incident_date"] = post["incident_id"].map(incident_dates)
    post["incident_date"] = pd.to_datetime(post["incident_date"])
    post["target_date"] = pd.to_datetime(post["target_date"])

    # Compute time gap in days
    post["time_gap_days"] = (post["target_date"] - post["incident_date"]).dt.days

    # Get FIRST post-incident acquisition per incident
    first_acq = post.loc[post.groupby("incident_id")["time_gap_days"].idxmin()]

    print("=" * 60)
    print("TIME GAP: Incident Date → First Post-Incident SAR Acquisition")
    print("=" * 60)
    print(f"\nIncidents with post-incident SAR: {len(first_acq)}")
    print(f"\nDescriptive statistics (days):")
    print(first_acq["time_gap_days"].describe().to_string())
    print(f"\nMedian gap: {first_acq['time_gap_days'].median():.0f} days")
    print(f"IQR: {first_acq['time_gap_days'].quantile(0.25):.0f}"
          f"–{first_acq['time_gap_days'].quantile(0.75):.0f} days")
    print(f"Range: {first_acq['time_gap_days'].min():.0f}"
          f"–{first_acq['time_gap_days'].max():.0f} days")

    # Also report ALL post-incident acquisition gaps
    print(f"\n--- All post-incident acquisitions ---")
    print(f"Total post-incident acquisitions: {len(post)}")
    print(f"Median gap: {post['time_gap_days'].median():.0f} days")
    print(f"IQR: {post['time_gap_days'].quantile(0.25):.0f}"
          f"–{post['time_gap_days'].quantile(0.75):.0f} days")

    # Baseline gap (pre-incident control distance)
    ctrl = diff[diff["pre_incident"]].copy()
    print(f"\n--- Pre-incident controls ---")
    print(f"Total control acquisitions: {len(ctrl)}")
    print(f"Baseline days before incident: "
          f"median={ctrl['baseline_days_before'].median():.0f}, "
          f"IQR={ctrl['baseline_days_before'].quantile(0.25):.0f}"
          f"–{ctrl['baseline_days_before'].quantile(0.75):.0f}")

    # Save a machine-readable summary for the paper / summary_stats.py.
    def q(x):
        return {"median": round(float(x.median()), 1),
                "q25": round(float(x.quantile(0.25)), 1),
                "q75": round(float(x.quantile(0.75)), 1),
                "min": round(float(x.min()), 1),
                "max": round(float(x.max()), 1),
                "n": int(len(x))}

    summary = {
        "first_post_acquisition_gap_days": q(first_acq["time_gap_days"]),
        "all_post_acquisition_gap_days": q(post["time_gap_days"]),
        "control_baseline_days_before": q(ctrl["baseline_days_before"]),
        "n_incidents_with_post_sar": int(len(first_acq)),
        "n_post_acquisitions": int(len(post)),
        "n_control_acquisitions": int(len(ctrl)),
    }

    import json
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nWrote {OUT_JSON}")


if __name__ == "__main__":
    main()
