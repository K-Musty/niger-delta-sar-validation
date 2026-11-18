#!/usr/bin/env python3
"""
Phase 2d — Anomaly candidate detection (v2 — stricter thresholds).

For each diff TIF:
    - Threshold: median - MIN_CONTRAST_DB (fixed, not percentile)
    - 8-connectivity clustering
    - Discard clusters < MIN_ANOMALY_PIXELS
    - Discard clusters whose mean diff is not at least MIN_CONTRAST_DB darker
      than the image median
    - Compute geodesic distance from centroid to reported NOSDRA coordinate
"""
from __future__ import annotations

import sys
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage
from geopy.distance import geodesic

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

DIFF_DIR   = config.DIFF_OUT
DIFF_CSV   = config.DATA_INTERIM / "per_acquisition_diff.csv"
CANDIDATES = config.DATA_INTERIM / "candidates_flagged.csv"
OUT_CSV    = config.DATA_INTERIM / "anomaly_candidates.csv"

# --- Detector parameters (from config.py) ---------------------------------
CONTRAST_DB      = config.CONTRAST_DB
MIN_CLUSTER_PX   = config.MIN_CLUSTER_PX
MIN_MEAN_DARK_DB = config.MIN_MEAN_DARK_DB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def pixel_to_lonlat(row: int, col: int, transform):
    x, y = transform * (col + 0.5, row + 0.5)
    return y, x


def main():
    cand = pd.read_csv(CANDIDATES)
    coord_lookup = {
        int(r["incident_id"]): (float(r["lat"]), float(r["lon"]))
        for _, r in cand.iterrows()
    }

    diff_meta = pd.read_csv(DIFF_CSV)
    log.info(f"Loaded {len(diff_meta)} diff records")
    log.info(f"Thresholds: contrast>={CONTRAST_DB} dB, "
             f"min_px={MIN_CLUSTER_PX}, "
             f"min_mean_dark>={MIN_MEAN_DARK_DB} dB")

    rows = []
    processed = 0
    failed = 0

    for _, rec in diff_meta.iterrows():
        iid = int(rec["incident_id"])
        diff_path = Path(rec["diff_path"])

        if not diff_path.exists() or iid not in coord_lookup:
            failed += 1
            continue

        rep_lat, rep_lon = coord_lookup[iid]

        try:
            with rasterio.open(diff_path) as src:
                arr = src.read(1).astype(np.float32)
                transform = src.transform
                nodata = src.nodata
        except Exception as e:
            log.warning(f"Open failed {diff_path.name}: {e}")
            failed += 1
            continue

        if nodata is not None:
            arr = np.where(arr == nodata, np.nan, arr)

        valid = np.isfinite(arr)
        if valid.sum() < 100:
            failed += 1
            continue

        med = float(np.nanmedian(arr))
        threshold = med - CONTRAST_DB

        mask = (arr < threshold) & valid

        structure = np.ones((3, 3), dtype=int)
        labels, n_clusters = ndimage.label(mask, structure=structure)

        if n_clusters == 0:
            processed += 1
            continue

        candidate_id = 0
        for cluster_id in range(1, n_clusters + 1):
            cluster_mask = labels == cluster_id
            area = int(cluster_mask.sum())
            if area < MIN_CLUSTER_PX:
                continue

            cluster_mean = float(np.nanmean(arr[cluster_mask]))
            if cluster_mean > (med - MIN_MEAN_DARK_DB):
                continue

            rr, cc = np.where(cluster_mask)
            row_c = float(rr.mean())
            col_c = float(cc.mean())
            lat_c, lon_c = pixel_to_lonlat(row_c, col_c, transform)

            try:
                dist_m = geodesic((lat_c, lon_c), (rep_lat, rep_lon)).meters
            except Exception:
                dist_m = float("nan")

            candidate_id += 1
            rows.append({
                "incident_id": iid,
                "baseline_date": rec["baseline_date"],
                "target_date": rec["target_date"],
                "pre_incident": bool(rec.get("pre_incident", False)),
                "days_after_incident": int(rec["days_after_incident"]),
                "candidate_id": candidate_id,
                "centroid_lat": lat_c,
                "centroid_lon": lon_c,
                "area_pixels": area,
                "mean_diff_db": cluster_mean,
                "median_image_db": med,
                "distance_from_reported_m": dist_m,
            })

        processed += 1

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False)

    log.info("=" * 60)
    log.info("PHASE 2D COMPLETE (v2)")
    log.info("=" * 60)
    log.info(f"Diffs processed:      {processed}")
    log.info(f"Failed:               {failed}")
    log.info(f"Candidate clusters:   {len(out)}")

    if len(out):
        log.info(f"Unique incidents:     {out['incident_id'].nunique()}")
        log.info(f"Post-incident:        {(~out['pre_incident']).sum()}")
        log.info(f"Pre-incident (ctrl):  {out['pre_incident'].sum()}")

        n_targets = (~diff_meta["pre_incident"]).sum()
        n_controls = diff_meta["pre_incident"].sum()
        n_post = (~out["pre_incident"]).sum()
        n_ctrl = out["pre_incident"].sum()

        log.info("")
        log.info(f"Detection rate per acquisition:")
        log.info(f"  Post-incident: {n_post}/{n_targets} = "
                 f"{n_post/max(n_targets,1):.3f}")
        log.info(f"  Pre-incident:  {n_ctrl}/{n_controls} = "
                 f"{n_ctrl/max(n_controls,1):.3f}")
        log.info("")
        log.info("Distance to reported coord (m):")
        log.info(out["distance_from_reported_m"].describe(
            percentiles=[.25, .5, .75, .9]).to_string())
        log.info("")
        log.info("Cluster area (pixels):")
        log.info(out["area_pixels"].describe(
            percentiles=[.25, .5, .75, .9]).to_string())


if __name__ == "__main__":
    main()
