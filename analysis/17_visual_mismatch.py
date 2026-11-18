#!/usr/bin/env python3
"""
Figure (V2 Figure 3): visual mismatch for incident 142357.

Three panels, all marking the reported NOSDRA coordinate with a yellow
circle:

  (a) pre-incident baseline backscatter (2018-10-03), dB
  (b) mean of the post-incident scenes (2018-10-22, 2018-10-27), dB
  (c) difference (post mean - baseline), dB, red = darkening

The extraction TIFs already hold sigma0 in dB (single float32 band,
EPSG:4326), so the panels can be rendered directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import rasterio
import rasterio.transform
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

INCIDENT_ID   = 142357
REP_LON       = 6.589444
REP_LAT       = 4.488889
BASELINE_DATE = "2018-10-03"
POST_DATES    = ["2018-10-22", "2018-10-27"]
OUT_PNG       = config.FIGURES / "figure_3_visual_mismatch.png"

BACKSCATTER_VMIN, BACKSCATTER_VMAX = -25.0, -5.0
DIFF_VMIN, DIFF_VMAX = -8.0, 8.0


def load_dates(iid, dates):
    arrs, transforms = [], []
    for d in dates:
        p = config.EXTRACTION_OUT / f"{iid}_{d}.tif"
        with rasterio.open(p) as src:
            arr = src.read(1).astype(np.float32)
            arr = np.where(np.isfinite(arr), arr, np.nan)
            transforms.append(src.transform)
        arrs.append(arr)
    return arrs, transforms


def mark_reported(ax, transform):
    """Draw a yellow circle at the reported coordinate in pixel space."""
    row, col = rasterio.transform.rowcol(transform, REP_LON, REP_LAT)
    ax.add_patch(Circle((col, row), radius=6, fill=False,
                        edgecolor="yellow", linewidth=2, zorder=5))


def main():
    (baseline,), transforms = load_dates(INCIDENT_ID, [BASELINE_DATE])
    post_arrs, _ = load_dates(INCIDENT_ID, POST_DATES)
    post_mean = np.nanmean(np.stack(post_arrs), axis=0)
    diff = post_mean - baseline
    transform = transforms[0]

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # Panels (a) and (b): backscatter in dB (gray).
    for ax, arr, title in zip(
        axes[:2],
        [baseline, post_mean],
        ["(a) Baseline 2018-10-03",
         "(b) Post-incident mean (10-22, 10-27)"],
    ):
        im = ax.imshow(arr, cmap="gray", vmin=BACKSCATTER_VMIN,
                       vmax=BACKSCATTER_VMAX, interpolation="nearest")
        mark_reported(ax, transform)
        ax.set_title(title, fontsize=11)
        ax.set_xticks([])
        ax.set_yticks([])

    # Panel (c): difference, red = darkening.
    cmap = plt.cm.RdBu_r
    im = axes[2].imshow(diff, cmap=cmap, vmin=DIFF_VMIN, vmax=DIFF_VMAX,
                        interpolation="nearest")
    mark_reported(axes[2], transform)
    axes[2].set_title("(c) Difference (post − baseline)", fontsize=11)
    axes[2].set_xticks([])
    axes[2].set_yticks([])

    cbar = fig.colorbar(im, ax=axes[2], fraction=0.046, pad=0.04)
    cbar.set_label("Backscatter change (dB)", fontsize=10)
    cbar.set_ticks([DIFF_VMIN, 0, DIFF_VMAX])
    cbar.set_ticklabels([f"{DIFF_VMIN:g} (darker)", "0",
                         f"{DIFF_VMAX:g} (brighter)"])

    fig.suptitle("Incident 142357 (Bayelsa, reported 2018-10-17, 1751 bbl) — "
                 "yellow circle = reported NOSDRA coordinate",
                 fontsize=12, y=1.02)

    plt.tight_layout()
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUT_PNG, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()

    print(f"Wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
