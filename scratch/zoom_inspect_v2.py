#!/usr/bin/env python3
"""
Zoomed inspection with corrected change detection.

Key changes from v1:
    - Minimum over window (oil is dark)
    - 3 km AOI (NOSDRA coordinate uncertainty)
    - Single closest acquisition before/after (fair comparison)
    - VV, VH, and VV/VH ratio (multi-channel diagnostic)
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import openeo

OUTPUT_DIR = Path("zoom_output_v2")
OUTPUT_DIR.mkdir(exist_ok=True)

INPUT_CSV = "candidates_flagged.csv"
PRIORITY_IDS = [118455, 142357, 236594, 281740, 229239, 190796, 222478]
ZOOM_BUFFER_DEG = 0.0135  # ~3 km x 3 km

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("zoom_inspect_v2.log", mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)


def load_window(connection, lat, lon, start_date, end_date):
    """
    Load all VV and VH acquisitions in window.
    Return dict: { 'vv': 2D array (minimum over time),
                   'vh': 2D array (minimum over time),
                   'n': number of acquisitions }
    """
    west = lon - ZOOM_BUFFER_DEG
    east = lon + ZOOM_BUFFER_DEG
    south = lat - ZOOM_BUFFER_DEG
    north = lat + ZOOM_BUFFER_DEG

    try:
        s1 = connection.load_collection(
            "SENTINEL1_GRD",
            spatial_extent={"west": west, "south": south,
                            "east": east, "north": north},
            temporal_extent=[start_date, end_date],
            bands=["VV", "VH"],
        )
        s1 = s1.sar_backscatter(
            coefficient="sigma0-ellipsoid",
            elevation_model="COPERNICUS_30",
            noise_removal=True,
        )
        s1_db = s1.apply(lambda x: 10 * x.log(base=10))

        job = s1_db.create_job(out_format="netCDF")
        job.start_and_wait()
        out_nc = OUTPUT_DIR / f"temp_{start_date}.nc"
        job.get_results().download_file(str(out_nc))

        import xarray as xr
        ds = xr.open_dataset(out_nc)
        time_dim = "t" if "t" in ds.dims else "time"

        # Find spatial vars
        spatial_vars = [v for v in ds.data_vars
                        if 'x' in ds[v].dims and 'y' in ds[v].dims]
        log.info(f"    Available vars: {spatial_vars}")

        result = {"n": len(ds[time_dim])}

        # Get VV
        vv_name = next((v for v in spatial_vars if 'VV' in v.upper()), None)
        if vv_name:
            # Minimum over time = darkest observation
            result["vv"] = ds[vv_name].min(dim=time_dim).values.astype(np.float32)

        # Get VH
        vh_name = next((v for v in spatial_vars
                        if 'VH' in v.upper() and 'VV' not in v.upper()), None)
        if vh_name:
            result["vh"] = ds[vh_name].min(dim=time_dim).values.astype(np.float32)

        ds.close()
        out_nc.unlink(missing_ok=True)
        return result

    except Exception as e:
        log.error(f"    Load failed: {e}")
        return None


def main():
    df = pd.read_csv(INPUT_CSV)
    df = df[df["incident_id"].isin(PRIORITY_IDS)]
    log.info(f"Processing {len(df)} priority incidents")

    connection = openeo.connect("openeo.dataspace.copernicus.eu")
    connection.authenticate_oidc()

    for idx, row in df.iterrows():
        iid = int(row["incident_id"])
        lat, lon = float(row["lat"]), float(row["lon"])
        state = row["final_state"]
        vol = row["volume"]
        inc_date = pd.to_datetime(row["date"]).to_pydatetime()

        log.info(f"[{iid}] {state} | {inc_date.date()} | {vol} bbl")

        # Baseline window: 20-40 days before
        base_start = (inc_date - timedelta(days=40)).strftime("%Y-%m-%d")
        base_end = (inc_date - timedelta(days=20)).strftime("%Y-%m-%d")

        # Spill window: 0-10 days after
        spill_start = inc_date.strftime("%Y-%m-%d")
        spill_end = (inc_date + timedelta(days=10)).strftime("%Y-%m-%d")

        log.info(f"  Baseline: {base_start} to {base_end}")
        base = load_window(connection, lat, lon, base_start, base_end)
        if base is None:
            log.warning(f"  No baseline for {iid}, skipping")
            continue

        log.info(f"  Spill: {spill_start} to {spill_end}")
        spill = load_window(connection, lat, lon, spill_start, spill_end)
        if spill is None:
            log.warning(f"  No spill window for {iid}, skipping")
            continue

        log.info(f"  Baseline n={base['n']}, Spill n={spill['n']}")

        # Make multi-panel figure
        fig, axes = plt.subplots(2, 3, figsize=(16, 10))

        # Row 1: VV baseline, VV spill, VV difference
        if "vv" in base and "vv" in spill:
            vv_b, vv_s = base["vv"], spill["vv"]
            h = min(vv_b.shape[0], vv_s.shape[0])
            w = min(vv_b.shape[1], vv_s.shape[1])
            vv_b, vv_s = vv_b[:h, :w], vv_s[:h, :w]
            vv_d = vv_s - vv_b

            vmin, vmax = np.nanpercentile(vv_b, [2, 98])
            axes[0][0].imshow(vv_b, cmap="gray", vmin=vmin, vmax=vmax)
            axes[0][0].set_title(f"VV baseline (min, n={base['n']})\n{base_start}")
            axes[0][0].axis("off")

            vmin, vmax = np.nanpercentile(vv_s, [2, 98])
            axes[0][1].imshow(vv_s, cmap="gray", vmin=vmin, vmax=vmax)
            axes[0][1].set_title(f"VV spill (min, n={spill['n']})\n{spill_start}")
            axes[0][1].axis("off")

            dmax = np.nanpercentile(np.abs(vv_d), 98)
            im = axes[0][2].imshow(vv_d, cmap="RdBu", vmin=-dmax, vmax=dmax)
            axes[0][2].set_title("VV diff (spill - baseline)")
            axes[0][2].axis("off")
            plt.colorbar(im, ax=axes[0][2], fraction=0.046)

        # Row 2: VH baseline, VH spill, VV/VH ratio
        if "vh" in base and "vh" in spill:
            vh_b, vh_s = base["vh"], spill["vh"]
            h = min(vh_b.shape[0], vh_s.shape[0])
            w = min(vh_b.shape[1], vh_s.shape[1])
            vh_b, vh_s = vh_b[:h, :w], vh_s[:h, :w]

            vmin, vmax = np.nanpercentile(vh_b, [2, 98])
            axes[1][0].imshow(vh_b, cmap="gray", vmin=vmin, vmax=vmax)
            axes[1][0].set_title(f"VH baseline (min, n={base['n']})")
            axes[1][0].axis("off")

            vmin, vmax = np.nanpercentile(vh_s, [2, 98])
            axes[1][1].imshow(vh_s, cmap="gray", vmin=vmin, vmax=vmax)
            axes[1][1].set_title(f"VH spill (min, n={spill['n']})")
            axes[1][1].axis("off")

            # VV/VH ratio
            if "vv" in spill and "vh" in spill:
                ratio = spill["vv"] - spill["vh"]  # in dB, difference = log ratio
                vmin, vmax = np.nanpercentile(ratio, [2, 98])
                im = axes[1][2].imshow(ratio, cmap="viridis", vmin=vmin, vmax=vmax)
                axes[1][2].set_title("VV - VH (dB)")
                axes[1][2].axis("off")
                plt.colorbar(im, ax=axes[1][2], fraction=0.046)

        # Mark incident location in all panels
        cy, cx = 500 // 2, 500 // 2
        for row_axes in axes:
            for ax in row_axes:
                if ax.has_data():
                    ax.plot(cx, cy, 'o', markersize=12,
                            markerfacecolor='none',
                            markeredgecolor='lime',
                            markeredgewidth=2)

        plt.suptitle(f"Incident {iid} | {state} | {vol} bbl | {inc_date.date()}",
                     fontsize=13)
        plt.tight_layout()
        out_png = OUTPUT_DIR / f"zoom_v2_{iid}.png"
        plt.savefig(out_png, dpi=100, bbox_inches="tight")
        plt.close()
        log.info(f"  Saved {out_png}")


if __name__ == "__main__":
    main()
