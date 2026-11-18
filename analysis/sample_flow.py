#!/usr/bin/env python3
"""
Phase 5 — Figure 1: sample flow from NOSDRA records to OBSERVABLE acquisitions.

Stage counts are read from data/output/stats.json (the single source of truth
produced by analysis/summary_stats.py). Only the upstream NOSDRA raw count
(21,167) is hardcoded — it is a fixed external number.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

STATS_JSON = config.DATA_OUTPUT / "stats.json"
OUT_PNG = PROJECT_ROOT / "figures" / "figure_2_sample_flow.png"
OUT_PNG.parent.mkdir(parents=True, exist_ok=True)


def main():
    with open(STATS_JSON) as f:
        st = json.load(f)

    sf = st["sample_flow"]

    stages = [
        ("NOSDRA raw records", sf["nosdra_raw_records"]),
        ("Filtered candidates (vol>=50, post-2015, NDDC, valid coords)",
         sf["filtered_candidates"]),
        ("Incidents with SAR data", sf["incidents_with_sar"]),
        ("Sentinel-1 acquisitions extracted", sf["acquisitions_extracted"]),
        ("Post-incident diffs (against pre-incident baseline)",
         sf["post_incident_diffs"]),
        ("OBSERVABLE_OPEN_WATER acquisitions (wind 3-12, no rain)",
         sf["observable_open_water"]),
        ("Acquisitions with distinguishable spill signal",
         sf["distinguishable_spills"]),
    ]

    fig, ax = plt.subplots(figsize=(13, 7))

    y_positions = list(range(len(stages)))[::-1]
    max_val = stages[0][1]

    for i, ((label, value), y) in enumerate(zip(stages, y_positions)):
        width = np.log10(value + 1) / np.log10(max_val + 1)
        color = "#1f77b4" if i < len(stages) - 1 else "#d62728"
        ax.barh(y, width, color=color, height=0.5, edgecolor="black")
        ax.text(width + 0.02, y, f"{value:,}", va="center", fontsize=10)
        ax.text(-0.02, y, label, va="center", ha="right", fontsize=9)

    ax.set_xlim(-0.6, 1.35)
    ax.set_ylim(-0.5, len(stages) - 0.5)
    ax.axis("off")
    ax.set_title("Sample flow from NOSDRA records to observable SAR acquisitions",
                 fontsize=12, pad=20)
    plt.tight_layout()
    plt.savefig(OUT_PNG, dpi=150, bbox_inches="tight")
    plt.close()

    print(f"Wrote {OUT_PNG}")


if __name__ == "__main__":
    main()

