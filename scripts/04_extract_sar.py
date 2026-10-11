#!/usr/bin/env python3
"""
Full Sentinel-1 extraction for all NOSDRA Niger Delta candidates.
Uses openEO temporal cube loading and date splitting — no STAC dependency.

For each incident:
    1. Load a Sentinel-1 GRD time cube over the +/- 14 day window.
    2. Apply sar_backscatter with noise removal.
    3. Convert to dB.
    4. Download as a NetCDF cube.
    5. Split the cube into individual date slices.
    6. Save each slice as a GeoTIFF and PNG.

Inputs:
    candidates_flagged.csv
Outputs:
    extraction_output/<incident_id>_<sar_date>.tif
    extraction_output/<incident_id>_<sar_date>.png
    extraction_log.csv
    extract_full.log
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

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
OUTPUT_DIR = Path("extraction_output")
OUTPUT_DIR.mkdir(exist_ok=True)

INPUT_CSV = "candidates_flagged.csv"
SEARCH_WINDOW_DAYS = 14
AOI_BUFFER_DEG = 0.0225  # ~5 km x 5 km at Niger Delta latitudes

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("extract_full.log", mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# PROCESS ONE INCIDENT
# ------------------------------------------------------------------
def process_incident(connection, row):
    incident_id = int(row["incident_id"])
    lat = float(row["lat"])
    lon = float(row["lon"])
    state = row["final_state"]
    incident_date = pd.to_datetime(row["date"]).to_pydatetime()

    west = lon - AOI_BUFFER_DEG
    east = lon + AOI_BUFFER_DEG
    south = lat - AOI_BUFFER_DEG
    north = lat + AOI_BUFFER_DEG

    start = (incident_date - timedelta(days=SEARCH_WINDOW_DAYS)).strftime("%Y-%m-%d")
    end = (incident_date + timedelta(days=SEARCH_WINDOW_DAYS)).strftime("%Y-%m-%d")

    log.info("=" * 70)
    log.info(f"Incident {incident_id} | {state} | {incident_date.date()}")
    log.info(f"  AOI: ({lat:.4f}, {lon:.4f}) | Window: {start} to {end}")
    log.info("=" * 70)

    # ------------------------------------------------------------------
    # Build the openEO process graph
    # ------------------------------------------------------------------
    try:
        s1 = connection.load_collection(
            "SENTINEL1_GRD",
            spatial_extent={"west": west, "south": south,
                            "east": east, "north": north},
            temporal_extent=[start, end],
            bands=["VV"],
        )
        s1 = s1.sar_backscatter(
            coefficient="sigma0-ellipsoid",
            elevation_model="COPERNICUS_30",
            noise_removal=True,
        )
        # Convert to dB: 10 * log10(x)
        s1_db = s1.apply(lambda x: 10 * x.log(base=10))
    except Exception as e:
        log.error(f"  Graph construction failed: {e}")
        return [{
            "incident_id": incident_id, "state": state,
            "incident_date": incident_date.date(),
            "sar_date": None, "days_after_incident": None,
            "status": "GRAPH_ERROR", "tif_file": None,
            "png_file": None, "error": str(e),
        }]

    # ------------------------------------------------------------------
    # Submit batch job, download NetCDF cube
    # ------------------------------------------------------------------
    out_nc = OUTPUT_DIR / f"{incident_id}_cube.nc"

    try:
        job = s1_db.create_job(out_format="netCDF")
        job.start_and_wait()
        job.get_results().download_file(str(out_nc))
        log.info(f"  Downloaded cube: {out_nc}")
    except Exception as e:
        log.error(f"  Batch job failed: {e}")
        return [{
            "incident_id": incident_id, "state": state,
            "incident_date": incident_date.date(),
            "sar_date": None, "days_after_incident": None,
            "status": "JOB_ERROR", "tif_file": None,
            "png_file": None, "error": str(e),
        }]

    # ------------------------------------------------------------------
    # Split cube into date slices
    # ------------------------------------------------------------------
    results = []
    try:
        import xarray as xr
        ds = xr.open_dataset(out_nc)

        # Detect the time dimension name
        time_dim = None
        for candidate in ["t", "time"]:
            if candidate in ds.dims:
                time_dim = candidate
                break
        if time_dim is None:
            raise RuntimeError(f"No time dimension found. Dims: {list(ds.dims)}")

        dates = pd.to_datetime(ds[time_dim].values)
        log.info(f"  Cube contains {len(dates)} time slices")

        # Find the actual SAR data variable (skip crs, spatial_ref, etc.)
        data_vars = []
        for v in ds.data_vars:
            da = ds[v]
            if 'x' in da.dims and 'y' in da.dims:
                data_vars.append(v)

        if not data_vars:
            raise RuntimeError(
                f"No spatial data variables found. "
                f"All data vars: {list(ds.data_vars)} "
                f"Dim info: {[(v, ds[v].dims) for v in ds.data_vars]}"
            )

        # Prefer 'VV' if present, else use the first spatial variable
        if 'VV' in data_vars:
            var_name = 'VV'
        else:
            var_name = data_vars[0]

        log.info(f"  Data variable: {var_name} (dims: {ds[var_name].dims})")

        for i, sar_dt in enumerate(dates):
            sar_date = sar_dt.strftime("%Y-%m-%d")
            days_after = (sar_dt.to_pydatetime() - incident_date).days

            slice_data = ds.isel({time_dim: i})
            da = slice_data[var_name]

            # Apply scale/offset if the NetCDF is packed as integers
            if hasattr(da, 'encoding') and 'scale_factor' in da.encoding:
                arr = da.astype(np.float32).values
            else:
                arr = da.values.astype(np.float32)

            # Squeeze out any residual singleton dimensions
            arr = np.squeeze(arr)

            # Skip empty slices
            if np.all(np.isnan(arr)):
                log.warning(f"  Skipping {sar_date} — all NaN")
                continue

            out_base = f"{incident_id}_{sar_date}"
            out_tif = OUTPUT_DIR / f"{out_base}.tif"
            out_png = OUTPUT_DIR / f"{out_base}.png"

            # Write GeoTIFF with LZW compression
            with rasterio.open(
                out_tif, "w",
                driver="GTiff",
                height=arr.shape[0],
                width=arr.shape[1],
                count=1,
                dtype="float32",
                compress="lzw",
                nodata=np.nan,
            ) as dst:
                dst.write(arr, 1)

            # PNG preview
            fig, ax = plt.subplots(figsize=(7, 6))
            im = ax.imshow(arr, cmap="gray", vmin=-25, vmax=0)
            plt.colorbar(im, ax=ax, label="Sigma0 (dB)")
            ax.set_title(f"Incident {incident_id} | {state}\n"
                         f"SAR: {sar_date} (+{days_after}d)")
            plt.savefig(out_png, dpi=100, bbox_inches="tight")
            plt.close()

            results.append({
                "incident_id": incident_id,
                "state": state,
                "incident_date": incident_date.date(),
                "sar_date": sar_date,
                "days_after_incident": days_after,
                "status": "SUCCESS",
                "tif_file": str(out_tif),
                "png_file": str(out_png),
                "error": None,
            })
            log.info(f"  -> {sar_date} (+{days_after}d) saved")

        ds.close()
        # Remove cube to save disk space
        out_nc.unlink(missing_ok=True)

    except Exception as e:
        log.error(f"  Splitting failed: {e}")
        results.append({
            "incident_id": incident_id, "state": state,
            "incident_date": incident_date.date(),
            "sar_date": None, "days_after_incident": None,
            "status": "SPLIT_ERROR", "tif_file": None,
            "png_file": None, "error": str(e),
        })
        # Clean up the cube on failure too
        try:
            out_nc.unlink(missing_ok=True)
        except Exception:
            pass

    return results

# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def main():
    if not os.path.exists(INPUT_CSV):
        log.error(f"Missing input: {INPUT_CSV}")
        sys.exit(1)

    df = pd.read_csv(INPUT_CSV)
    log.info(f"Loaded {len(df)} candidate incidents")

    log.info("Connecting to Copernicus openEO backend...")
    connection = openeo.connect("openeo.dataspace.copernicus.eu")
    log.info("Authenticating...")
    connection.authenticate_oidc()
    log.info("Authenticated")

    all_results = []

    for idx, row in df.iterrows():
        log.info(f"[{idx+1}/{len(df)}]")
        try:
            results = process_incident(connection, row)
            all_results.extend(results)
        except Exception as e:
            log.exception(f"Unexpected error on incident {row['incident_id']}")
            all_results.append({
                "incident_id": int(row["incident_id"]),
                "state": row["final_state"],
                "incident_date": row["date"],
                "sar_date": None,
                "days_after_incident": None,
                "status": "UNEXPECTED_ERROR",
                "tif_file": None,
                "png_file": None,
                "error": str(e),
            })

    summary = pd.DataFrame(all_results)
    summary.to_csv("extraction_log.csv", index=False)

    log.info("=" * 70)
    log.info("EXTRACTION COMPLETE")
    log.info("=" * 70)
    log.info(f"Total attempts: {len(summary)}")
    log.info(f"Success:        {(summary['status'] == 'SUCCESS').sum()}")
    log.info(f"Errors:         {summary['status'].str.endswith('ERROR').sum()}")
    log.info(f"Output dir:     {OUTPUT_DIR.resolve()}")

if __name__ == "__main__":
    main()
