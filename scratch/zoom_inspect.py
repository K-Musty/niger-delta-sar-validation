#!/usr/bin/env python3
"""
Zoomed inspection + change detection for priority spill incidents.
Produces side-by-side pre-spill / post-spill / difference plots.
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
import rasterio
import openeo

OUTPUT_DIR = Path("zoom_output")
OUTPUT_DIR.mkdir(exist_ok=True)

INPUT_CSV = "candidates_flagged.csv"
PRIORITY_IDS = [118455, 142357, 236594, 281740, 229239, 190796, 222478]
ZOOM_BUFFER_DEG = 0.0045  # ~500m x 500m

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("zoom_inspect.log", mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)


def load_patch(connection, lat, lon, start_date, end_date):
    """Load a zoomed SAR patch. Returns array or None."""
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
            bands=["VV"],
        )
        s1 = s1.sar_backscatter(
            coefficient="sigma0-ellipsoid",
            elevation_model="COPERNICUS_30",
            noise_removal=True,
        )
        s1_db = s1.apply(lambda x: 10 * x.log(base=10))

        job = s1_db.create_job(out_format="netCDF")
        job.start_and_wait()
        out_nc = OUTPUT_DIR / "temp.nc"
        job.get_results().download_file(str(out_nc))

        import xarray as xr
        ds = xr.open_dataset(out_nc)
        time_dim = "t" if "t" in ds.dims else "time"

        # Get spatial data variable
        data_vars = [v for v in ds.data_vars
                     if 'x' in ds[v].dims and 'y' in ds[v].dims]
        var_name = 'VV' if 'VV' in data_vars else data_vars[0]

        # Get the median of all time slices to reduce speckle
        arr = ds[var_name].median(dim=time_dim).values.astype(np.float32)
        ds.close()
        out_nc.unlink(missing_ok=True)
        return arr

    except Exception as e:
        log.error(f"  Load failed: {e}")
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

        # Baseline: 30-60 days BEFORE incident
        base_start = (inc_date - timedelta(days=60)).strftime("%Y-%m-%d")
        base_end = (inc_date - timedelta(days=30)).strftime("%Y-%m-%d")

        # Spill window: 0-14 days after incident
        spill_start = inc_date.strftime("%Y-%m-%d")
        spill_end = (inc_date + timedelta(days=14)).strftime("%Y-%m-%d")

        log.info(f"  Loading baseline: {base_start} to {base_end}")
        base = load_patch(connection, lat, lon, base_start, base_end)

        log.info(f"  Loading spill window: {spill_start} to {spill_end}")
        spill = load_patch(connection, lat, lon, spill_start, spill_end)

        if base is None or spill is None:
            log.warning(f"  Skipping {iid} — missing data")
            continue

        # Align shapes
        h = min(base.shape[0], spill.shape[0])
        w = min(base.shape[1], spill.shape[1])
        base = base[:h, :w]
        spill = spill[:h, :w]

        # Difference: negative values = darkening (spill candidate)
        diff = spill - base

        # Make figure
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))

        vmin, vmax = np.nanpercentile(base, [2, 98])
        axes[0].imshow(base, cmap="gray", vmin=vmin, vmax=vmax)
        axes[0].set_title(f"Baseline (pre-spill)\n{base_start} to {base_end}")
        axes[0].axis("off")

        vmin, vmax = np.nanpercentile(spill, [2, 98])
        axes[1].imshow(spill, cmap="gray", vmin=vmin, vmax=vmax)
        axes[1].set_title(f"Spill window\n{spill_start} to {spill_end}")
        axes[1].axis("off")

        # Difference: diverging colormap, centered on 0
        dmax = np.nanpercentile(np.abs(diff), 98)
        im = axes[2].imshow(diff, cmap="RdBu", vmin=-dmax, vmax=dmax)
        axes[2].set_title("Difference (spill - baseline)\nRed = darkening = candidate spill")
        axes[2].axis("off")
        plt.colorbar(im, ax=axes[2], fraction=0.046)

        # Mark the incident coordinate (center of the image)
        cy, cx = h // 2, w // 2
        for ax in axes:
            ax.plot(cx, cy, 'yo', markersize=15, markerfacecolor='none',
                    markeredgewidth=2)

        plt.suptitle(f"Incident {iid} | {state} | {vol} bbl | {inc_date.date()}")
        plt.tight_layout()
        out_png = OUTPUT_DIR / f"zoom_{iid}.png"
        plt.savefig(out_png, dpi=110, bbox_inches="tight")
        plt.close()
        log.info(f"  Saved {out_png}")


if __name__ == "__main__":
    main()
