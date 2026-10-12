#!/usr/bin/env python3
"""
Phase 2c — Per-acquisition change detection.

For each incident:
    - Baseline = acquisition closest to (incident_date - 45 days), strictly pre-incident
    - For every other acquisition (target), compute diff = target - baseline
    - Save GeoTIFF (float32, LZW, EPSG:4326, baseline geotransform)

Outputs:
    artifacts/diff_output/<iid>_<baseline>_<target>.tif
    data/interim/per_acquisition_diff.csv
    logs/skipped_no_baseline.txt
    logs/skipped_single_acq.txt
    logs/skipped_shape_mismatch.txt
"""
from __future__ import annotations

import sys
import logging
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

INPUT_TIF_DIR = config.EXTRACTION_OUT
OUT_TIF_DIR   = config.DIFF_OUT
OUT_CSV       = config.DATA_INTERIM / "per_acquisition_diff.csv"
CANDIDATES    = config.DATA_INTERIM / "candidates_flagged.csv"

LOG_DIR = config.LOGS
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

OUT_TIF_DIR.mkdir(parents=True, exist_ok=True)


def parse_date_from_tif(path: Path) -> str | None:
    """Extract YYYY-MM-DD from filename <incident_id>_<date>.tif"""
    stem = path.stem
    parts = stem.split("_")
    if len(parts) < 2:
        return None
    return parts[-1]  # assumes date is the last underscore-separated token


def parse_incident_from_tif(path: Path) -> int | None:
    stem = path.stem
    parts = stem.split("_")
    if not parts:
        return None
    try:
        return int(parts[0])
    except ValueError:
        return None


def write_diff(out_path: Path,
               arr: np.ndarray,
               profile: dict) -> None:
    """Write diff as float32 GeoTIFF, LZW, preserving geotransform + CRS."""
    profile = dict(profile)
    profile.update(
        driver="GTiff",
        dtype="float32",
        count=1,
        compress="lzw",
        nodata=np.nan,
    )
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(arr.astype(np.float32), 1)


def main() -> None:
    cand = pd.read_csv(CANDIDATES)
    cand["incident_date"] = pd.to_datetime(cand["date"])
    incident_dates = dict(zip(cand["incident_id"], cand["incident_date"]))

    # Group TIFs by incident
    by_incident: dict[int, list[Path]] = {}
    for tif in INPUT_TIF_DIR.glob("*.tif"):
        iid = parse_incident_from_tif(tif)
        if iid is None:
            continue
        by_incident.setdefault(iid, []).append(tif)

    log.info(f"Found {sum(len(v) for v in by_incident.values())} TIFs "
             f"across {len(by_incident)} incidents")

    rows = []
    skip_no_baseline = []
    skip_single = []
    skip_shape = []

    for iid, tifs in sorted(by_incident.items()):
        # Sort by date
        dated = sorted(
            [(parse_date_from_tif(t), t) for t in tifs],
            key=lambda x: x[0],
        )
        dated = [(d, t) for d, t in dated if d is not None]

        if len(dated) < 2:
            skip_single.append(iid)
            continue

        inc_date = incident_dates.get(iid)
        if inc_date is None:
            log.warning(f"  Incident {iid} has no incident_date; skipping")
            skip_no_baseline.append(iid)
            continue

        # Pre-incident acquisitions only
        pre = [(d, t) for d, t in dated
               if pd.Timestamp(d) < inc_date]
        if not pre:
            skip_no_baseline.append(iid)
            continue

        target_anchor = inc_date - timedelta(days=45)
        baseline_date, baseline_tif = min(
            pre,
            key=lambda x: abs(pd.Timestamp(x[0]) - target_anchor),
        )

        with rasterio.open(baseline_tif) as src:
            baseline_arr = src.read(1).astype(np.float32)
            baseline_profile = src.profile.copy()
            baseline_crs = src.crs
            baseline_transform = src.transform

        # Skip anything at or before baseline date
        targets = [(d, t) for d, t in dated
                   if pd.Timestamp(d) > pd.Timestamp(baseline_date)]

        log.info(f"[{iid}] baseline={baseline_date}, "
                 f"targets={len(targets)}")

        for target_date, target_tif in targets:
            with rasterio.open(target_tif) as src:
                target_arr = src.read(1).astype(np.float32)

            # Shape check
            if target_arr.shape != baseline_arr.shape:
                h = min(baseline_arr.shape[0], target_arr.shape[0])
                w = min(baseline_arr.shape[1], target_arr.shape[1])
                skip_shape.append((iid, baseline_date, target_date,
                                   baseline_arr.shape, target_arr.shape))
                baseline_arr_c = baseline_arr[:h, :w]
                target_arr_c = target_arr[:h, :w]
                # Update profile for clipped shape
                profile_c = dict(baseline_profile)
                profile_c.update(height=h, width=w)
            else:
                baseline_arr_c = baseline_arr
                target_arr_c = target_arr
                profile_c = baseline_profile

            diff = target_arr_c - baseline_arr_c

            # Clean NaNs
            valid = np.isfinite(diff)
            if not valid.any():
                log.warning(f"  {iid} {baseline_date}->{target_date}: all NaN")
                continue

            diff_clean = np.where(valid, diff, np.nan)

            out_name = f"{iid}_{baseline_date}_{target_date}.tif"
            out_path = OUT_TIF_DIR / out_name
            write_diff(out_path, diff_clean, profile_c)

            days_after = (pd.Timestamp(target_date) - inc_date).days
            days_before = (inc_date - pd.Timestamp(baseline_date)).days

            rows.append({
                "incident_id": iid,
                "baseline_date": baseline_date,
                "target_date": target_date,
                "diff_path": str(out_path),
                "days_after_incident": days_after,
                "baseline_days_before": days_before,
                "mean_diff": float(np.nanmean(diff_clean)),
                "min_diff": float(np.nanmin(diff_clean)),
                "p05_diff": float(np.nanpercentile(diff_clean, 5)),
            })

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False)

    # Log skips
    with open(LOG_DIR / "skipped_no_baseline.txt", "w") as f:
        for iid in skip_no_baseline:
            f.write(f"{iid}\n")
    with open(LOG_DIR / "skipped_single_acq.txt", "w") as f:
        for iid in skip_single:
            f.write(f"{iid}\n")
    with open(LOG_DIR / "skipped_shape_mismatch.txt", "w") as f:
        for entry in skip_shape:
            f.write(repr(entry) + "\n")

    log.info("=" * 60)
    log.info("PHASE 2C COMPLETE")
    log.info("=" * 60)
    log.info(f"Diff TIFs written:    {len(rows)}")
    log.info(f"Unique incidents:     {out['incident_id'].nunique() if len(out) else 0}")
    log.info(f"Skipped (no baseline): {len(skip_no_baseline)}")
    log.info(f"Skipped (single acq):  {len(skip_single)}")
    log.info(f"Shape mismatches:      {len(skip_shape)}")


if __name__ == "__main__":
    main()
