#!/usr/bin/env python3
"""
Phase 4 — Figure 2: distance from reported coordinate to nearest SAR
anomaly candidate, plotted against days-after-incident, colored by habitat.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

CAND_CSV = config.DATA_INTERIM / "anomaly_candidates.csv"
INSP_CSV = config.DATA_INTERIM / "inspection_done.csv"
OUT_PNG  = PROJECT_ROOT / "figures" / "figure_2_distance_vs_time.png"
OUT_PNG.parent.mkdir(parents=True, exist_ok=True)


def main():
    cand = pd.read_csv(CAND_CSV)
    insp = pd.read_csv(INSP_CSV)
    habitat = dict(zip(insp["incident_id"], insp["habitat_group"]))

    cand["habitat_group"] = cand["incident_id"].map(habitat).fillna("unknown")

    # Aggregate: nearest candidate per (incident_id, target_date)
    nearest = (cand.groupby(["incident_id", "target_date", "pre_incident",
                             "days_after_incident", "habitat_group"])
               .agg(min_distance_m=("distance_from_reported_m", "min"),
                    n_clusters=("candidate_id", "count"))
               .reset_index())

    fig, ax = plt.subplots(figsize=(10, 6))

    colors = {
        "open_water": "#1f77b4",
        "swamp":      "#2ca02c",
        "land":       "#d62728",
        "unknown":    "#7f7f7f",
    }

    for h in ["open_water", "swamp", "land", "unknown"]:
        sub = nearest[nearest["habitat_group"] == h]
        if len(sub) == 0:
            continue
        post = sub[~sub["pre_incident"]]
        pre  = sub[sub["pre_incident"]]
        if len(post):
            ax.scatter(post["days_after_incident"], post["min_distance_m"],
                       label=f"{h} (post)", alpha=0.7, s=40,
                       c=colors[h], edgecolors="none")
        if len(pre):
            ax.scatter(pre["days_after_incident"], pre["min_distance_m"],
                       label=f"{h} (control)", alpha=0.4, s=30,
                       c=colors[h], marker="x", edgecolors="none")

    ax.axvline(0, color="black", linestyle="--", linewidth=0.7,
               label="Incident date")
    ax.set_xlabel("Days after reported incident date")
    ax.set_ylabel("Distance to nearest candidate anomaly (m)")
    ax.set_title("Figure 2 — Distance from NOSDRA coordinate to nearest SAR anomaly candidate")
    ax.legend(loc="upper right", fontsize=8, framealpha=0.9)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_PNG, dpi=150)
    plt.close()

    print(f"Wrote {OUT_PNG}")
    print(f"Points: {len(nearest)}")
    print(f"  Post-incident: {(~nearest['pre_incident']).sum()}")
    print(f"  Pre-incident:  {nearest['pre_incident'].sum()}")


if __name__ == "__main__":
    main()
