#!/usr/bin/env python3
"""
Synthetic-injection amplitude sweep (reviewer point A5).

Re-runs the positive control at peak amplitudes 5.0, 5.5, 6.0, 6.5, 7.0, 8.0 dB
using the SAME injection sites and the SAME (baseline, target) pairs at every
amplitude, so the only thing that varies is the injected contrast. This
characterises detection probability near the 5 dB detector threshold instead of
the single 8 dB point reported in the paper.

Recovery = a detected cluster centroid within 500 m of the injection centre.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from scipy import ndimage
from geopy.distance import geodesic

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402


def load_detector_constants():
    spec = importlib.util.spec_from_file_location(
        "detect08", PROJECT_ROOT / "scripts" / "08_detect_anomaly_candidates.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.CONTRAST_DB, m.MIN_CLUSTER_PX, m.MIN_MEAN_DARK_DB


CONTRAST_DB, MIN_CLUSTER_PX, MIN_MEAN_DARK_DB = load_detector_constants()

N_TEST = 20
AMPLITUDES_DB = [5.0, 5.5, 6.0, 6.5, 7.0, 8.0]
INJECT_SIGMA_PX = 10
INJECT_MARGIN_PX = 80
CLEAN_RADIUS_PX = 15
LOCAL_STD_MAX_DB = 3.0
PRE_EXISTING_DB = CONTRAST_DB
RECOVERY_RADIUS_M = 500
RANDOM_SEED = 42

OUT_CSV = config.DATA_OUTPUT / "injection_sweep.csv"


def find_injection_site(raw_diff, rng, max_attempts=300):
    h, w = raw_diff.shape
    valid = raw_diff[np.isfinite(raw_diff)]
    if valid.size < 1000:
        return None
    global_median = float(np.median(valid))
    thresh = global_median - PRE_EXISTING_DB
    yy, xx = np.ogrid[:h, :w]
    best = None
    for _ in range(max_attempts):
        cy = int(rng.integers(INJECT_MARGIN_PX, h - INJECT_MARGIN_PX))
        cx = int(rng.integers(INJECT_MARGIN_PX, w - INJECT_MARGIN_PX))
        mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= CLEAN_RADIUS_PX ** 2
        local = raw_diff[mask]
        local = local[np.isfinite(local)]
        if local.size < 50:
            continue
        s = float(local.std())
        if best is None or s < best[2]:
            best = (cy, cx, s)
        if s < LOCAL_STD_MAX_DB and float(local.min()) > thresh:
            return cy, cx, False
    return (best[0], best[1], True) if best else None


def apply_detector(diff, transform):
    valid = diff[np.isfinite(diff)]
    if valid.size < 1000:
        return []
    median_db = float(np.median(valid))
    dark = np.isfinite(diff) & (diff < (median_db - CONTRAST_DB))
    labeled, n = ndimage.label(dark, structure=np.ones((3, 3)))
    out = []
    for lab in range(1, n + 1):
        cm = labeled == lab
        area = int(cm.sum())
        if area < MIN_CLUSTER_PX:
            continue
        if float(diff[cm].mean()) > (median_db - MIN_MEAN_DARK_DB):
            continue
        ys, xs = np.where(cm)
        lon, lat = rasterio.transform.xy(transform, ys.mean(), xs.mean())
        out.append((float(lat), float(lon)))
    return out


def main():
    pairs = pd.read_csv(config.DATA_INTERIM / "per_acquisition_diff.csv")
    pairs = pairs.groupby("incident_id", group_keys=False).head(1).head(N_TEST).reset_index(drop=True)

    rng = np.random.default_rng(RANDOM_SEED)
    # pre-load arrays + fixed injection sites once
    loaded = []
    for _, row in pairs.iterrows():
        iid = int(row["incident_id"])
        bp = config.EXTRACTION_OUT / f"{iid}_{row['baseline_date']}.tif"
        tp = config.EXTRACTION_OUT / f"{iid}_{row['target_date']}.tif"
        if not (bp.exists() and tp.exists()):
            continue
        with rasterio.open(bp) as s:
            B = s.read(1).astype(np.float32); transform = s.transform
        with rasterio.open(tp) as s:
            T = s.read(1).astype(np.float32)
        if B.shape != T.shape:
            continue
        raw = T - B
        site = find_injection_site(raw, rng)
        if site is None:
            continue
        cy, cx, fallback = site
        inj_lon, inj_lat = rasterio.transform.xy(transform, cy, cx)
        loaded.append({
            "iid": iid, "B": B, "T": T, "transform": transform,
            "cy": cy, "cx": cx, "inj_lat": float(inj_lat), "inj_lon": float(inj_lon),
        })

    h, w = loaded[0]["T"].shape if loaded else (0, 0)
    rows = []
    for amp in AMPLITUDES_DB:
        rec = 0; dists = []
        for d in loaded:
            yy, xx = np.mgrid[0:d["T"].shape[0], 0:d["T"].shape[1]]
            blob = np.exp(-(((yy - d["cy"]) ** 2 + (xx - d["cx"]) ** 2)
                            / (2 * INJECT_SIGMA_PX ** 2))).astype(np.float32)
            inj_diff = (d["T"] - amp * blob) - d["B"]
            cl = apply_detector(inj_diff, d["transform"])
            if not cl:
                continue
            best = min(geodesic((d["inj_lat"], d["inj_lon"]), c).meters for c in cl)
            if best < RECOVERY_RADIUS_M:
                rec += 1
                dists.append(best)
        rows.append({
            "amplitude_db": amp,
            "n_sites": len(loaded),
            "n_recovered": rec,
            "detection_prob": round(rec / len(loaded), 3),
            "median_loc_error_m": round(float(np.median(dists)), 1) if dists else None,
        })
        print(f"{amp} dB: {rec}/{len(loaded)} recovered "
              f"({rec/len(loaded):.0%})"
              + (f", median loc err {np.median(dists):.0f} m" if dists else ""))

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False)
    print(f"\nSaved to {OUT_CSV}")


if __name__ == "__main__":
    main()
