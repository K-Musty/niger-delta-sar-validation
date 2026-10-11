#!/usr/bin/env python3
"""
Add CRS and geotransform to all extracted GeoTIFFs.

The openEO NetCDF output has no georeferencing. We reconstruct it from:
    - the AOI bounds we requested (incident lat/lon +/- AOI_BUFFER_DEG)
    - the array shape (height, width)
    - the CRS of the request (EPSG:4326)

Reads:  extraction_output/*.tif
Writes: same files, overwritten with georeferencing
Logs:   georeference.log
"""

import os
import sys
import logging
from pathlib import Path

import pandas as pd
import numpy as np
import rasterio
from rasterio.transform import from_origin

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
INPUT_CSV = "candidates_flagged.csv"
TIF_DIR = Path("extraction_output")
AOI_BUFFER_DEG = 0.0225
CRS = "EPSG:4326"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("georeference.log", mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def main():
    if not os.path.exists(INPUT_CSV):
        log.error(f"Missing: {INPUT_CSV}")
        sys.exit(1)

    df = pd.read_csv(INPUT_CSV)
    log.info(f"Loaded {len(df)} incidents from {INPUT_CSV}")

    # Build lookup: incident_id -> (lat, lon)
    coord_lookup = {}
    for _, row in df.iterrows():
        coord_lookup[int(row["incident_id"])] = (float(row["lat"]), float(row["lon"]))

    # Find all TIFs
    tifs = sorted(TIF_DIR.glob("*.tif"))
    log.info(f"Found {len(tifs)} TIF files")

    fixed = 0
    skipped = 0
    failed = 0

    for tif_path in tifs:
        # Filename format: <incident_id>_<YYYY-MM-DD>.tif
        stem = tif_path.stem
        parts = stem.split("_")
        if len(parts) < 2:
            log.warning(f"  Skipping (bad name): {tif_path.name}")
            skipped += 1
            continue

        try:
            incident_id = int(parts[0])
        except ValueError:
            log.warning(f"  Skipping (non-numeric ID): {tif_path.name}")
            skipped += 1
            continue

        if incident_id not in coord_lookup:
            log.warning(f"  No coordinates for incident {incident_id}")
            skipped += 1
            continue

        lat, lon = coord_lookup[incident_id]

        # Compute AOI bounds
        west = lon - AOI_BUFFER_DEG
        east = lon + AOI_BUFFER_DEG
        south = lat - AOI_BUFFER_DEG
        north = lat + AOI_BUFFER_DEG

        try:
            with rasterio.open(tif_path) as src:
                arr = src.read(1)
                h, w = arr.shape
                profile = src.profile.copy()

            # Compute pixel size
            xres = (east - west) / w
            yres = -(north - south) / h  # negative: raster origin is top-left

            # Construct affine transform: (west, north) is top-left corner
            transform = from_origin(west, north, xres, abs(yres))

            # Write back with CRS + transform
            profile.update({
                "crs": CRS,
                "transform": transform,
            })

            with rasterio.open(tif_path, "w", **profile) as dst:
                dst.write(arr, 1)

            fixed += 1
            log.info(f"  {tif_path.name}: {w}x{h}, "
                     f"xres={xres:.8f}, yres={yres:.8f}, "
                     f"origin=({west:.4f}, {north:.4f})")

        except Exception as e:
            log.error(f"  FAILED {tif_path.name}: {e}")
            failed += 1

    log.info("=" * 60)
    log.info("GEOREFERENCE COMPLETE")
    log.info("=" * 60)
    log.info(f"Fixed:   {fixed}")
    log.info(f"Skipped: {skipped}")
    log.info(f"Failed:  {failed}")

if __name__ == "__main__":
    main()
