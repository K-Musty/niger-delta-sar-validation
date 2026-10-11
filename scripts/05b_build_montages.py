#!/usr/bin/env python3
"""
Build temporal montage pages for visual inspection of extracted patches.

For each incident, all date slices are arranged in a horizontal row.
Four incidents per page. Pages saved to montage_pages/.
"""

import os
import sys
import logging
from pathlib import Path
from collections import defaultdict

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

TIF_DIR = Path("extraction_output")
PNG_DIR = Path("extraction_output")
OUT_DIR = Path("montage_pages")
OUT_DIR.mkdir(exist_ok=True)

INCIDENTS_PER_PAGE = 4

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger(__name__)

def main():
    # Group PNGs by incident_id
    pngs = sorted(PNG_DIR.glob("*.png"))
    log.info(f"Found {len(pngs)} PNG files")

    by_incident = defaultdict(list)
    for p in pngs:
        stem = p.stem  # <incident_id>_<date>
        parts = stem.split("_")
        if len(parts) < 2:
            continue
        try:
            incident_id = int(parts[0])
            date_str = parts[1]
        except ValueError:
            continue
        by_incident[incident_id].append((date_str, p))

    # Sort each incident's slices by date
    for iid in by_incident:
        by_incident[iid].sort(key=lambda x: x[0])

    incidents = sorted(by_incident.keys())
    log.info(f"Found {len(incidents)} incidents with PNGs")

    # Build pages
    page_num = 0
    for start in range(0, len(incidents), INCIDENTS_PER_PAGE):
        page_num += 1
        page_incidents = incidents[start:start + INCIDENTS_PER_PAGE]

        max_cols = max(len(by_incident[iid]) for iid in page_incidents)

        fig, axes = plt.subplots(
            len(page_incidents), max_cols,
            figsize=(max_cols * 3.2, len(page_incidents) * 3.4),
            squeeze=False,
        )

        for row_idx, iid in enumerate(page_incidents):
            slices = by_incident[iid]
            for col_idx in range(max_cols):
                ax = axes[row_idx][col_idx]
                if col_idx < len(slices):
                    date_str, png_path = slices[col_idx]
                    try:
                        img = mpimg.imread(png_path)
                        ax.imshow(img)
                        ax.set_title(f"{date_str}", fontsize=9)
                    except Exception as e:
                        ax.text(0.5, 0.5, f"ERR\n{e}", ha="center",
                                va="center", fontsize=7)
                    ax.axis("off")
                else:
                    ax.axis("off")

            # Label the row with the incident ID on the far left
            axes[row_idx][0].set_ylabel(
                f"Incident {iid}",
                fontsize=10, rotation=0,
                ha="right", va="center", labelpad=40
            )

        out_path = OUT_DIR / f"page_{page_num:02d}.png"
        plt.suptitle(f"Temporal montage — page {page_num} "
                     f"(incidents {page_incidents[0]}–{page_incidents[-1]})",
                     fontsize=11)
        plt.tight_layout()
        plt.savefig(out_path, dpi=90, bbox_inches="tight")
        plt.close()
        log.info(f"  Saved {out_path}")

    log.info("=" * 60)
    log.info(f"Done. {page_num} pages written to {OUT_DIR}/")
    log.info("Open them in your file browser and inspect visually.")

if __name__ == "__main__":
    main()
