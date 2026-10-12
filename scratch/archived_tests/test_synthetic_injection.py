#!/usr/bin/env python3
"""
Synthetic positive control for the Niger Delta SAR change detection pipeline.

v2 — relaxed clean-site criterion. The original version required all pixels
within a 30 px radius to have |diff| < 1 dB, which is impossible given SAR
speckle. The revised criterion only requires:
  (a) local diff std < 3 dB, and
  (b) no pre-existing cluster-forming pixels within 15 px of the site.

If no site meets this after 300 attempts, we fall back to a random interior
location and record that fallback in the log.
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


# ---------------------------------------------------------------------------
# Import detector constants from the actual pipeline script
# ---------------------------------------------------------------------------
def load_detector_constants():
    spec = importlib.util.spec_from_file_location(
        "detect08",
        PROJECT_ROOT / "scripts" / "08_detect_anomaly_candidates.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CONTRAST_DB, module.MIN_CLUSTER_PX, module.MIN_MEAN_DARK_DB


CONTRAST_DB, MIN_CLUSTER_PX, MIN_MEAN_DARK_DB = load_detector_constants()
print("Detector parameters (imported from scripts/08):")
print(f"  CONTRAST_DB      = {CONTRAST_DB}")
print(f"  MIN_CLUSTER_PX   = {MIN_CLUSTER_PX}")
print(f"  MIN_MEAN_DARK_DB = {MIN_MEAN_DARK_DB}")
print()

# ---------------------------------------------------------------------------
# Injection configuration
# ---------------------------------------------------------------------------
N_TEST = 20
INJECT_AMPLITUDE_DB = 8.0    # peak contrast, well above 5 dB threshold and above speckle
INJECT_SIGMA_PX = 10         # Gaussian sigma; effective area above threshold ≈ 250 px
INJECT_MARGIN_PX = 80        # keep blob away from image edges
CLEAN_RADIUS_PX = 15         # smaller radius; speckle makes larger radii impossible
LOCAL_STD_MAX_DB = 3.0       # local noise floor tolerance
PRE_EXISTING_DB = CONTRAST_DB  # exclude sites where pre-existing cluster is forming
RECOVERY_RADIUS_M = 500      # nearest cluster within this distance counts as recovered
RANDOM_SEED = 42

OUT_DIR = PROJECT_ROOT / "tests" / "synthetic_output"
OUT_DIR.mkdir(parents=True, exist_ok=True)
INJECTION_LOG = OUT_DIR / "injection_log.csv"
RECOVERY_LOG = OUT_DIR / "recovery_results.csv"

# ---------------------------------------------------------------------------
# Load candidate (baseline, target) pairs
# ---------------------------------------------------------------------------
DIFF_CSV = config.DATA_INTERIM / "per_acquisition_diff.csv"
pairs = pd.read_csv(DIFF_CSV)
print(f"Loaded {len(pairs)} pairs from {DIFF_CSV}")

# Group by incident so we don't over-represent a single incident
pairs = pairs.groupby("incident_id", group_keys=False).head(1)
pairs = pairs.head(N_TEST).reset_index(drop=True)
print(f"Selected {len(pairs)} pairs across {pairs['incident_id'].nunique()} incidents")
print()

# ---------------------------------------------------------------------------
# Diagnostic: measure the actual diff distribution once
# ---------------------------------------------------------------------------
_first = pairs.iloc[0]
_b = config.EXTRACTION_OUT / f"{int(_first['incident_id'])}_{_first['baseline_date']}.tif"
_t = config.EXTRACTION_OUT / f"{int(_first['incident_id'])}_{_first['target_date']}.tif"
if _b.exists() and _t.exists():
    with rasterio.open(_b) as s:
        _B = s.read(1).astype(np.float32)
    with rasterio.open(_t) as s:
        _T = s.read(1).astype(np.float32)
    _d = _T - _B
    _d = _d[np.isfinite(_d)]
    print("Diagnostic — first diff distribution:")
    print(f"  n        = {_d.size}")
    print(f"  median   = {np.median(_d):+.2f} dB")
    print(f"  std      = {_d.std():.2f} dB")
    print(f"  p05/p95  = {np.percentile(_d, 5):+.2f} / {np.percentile(_d, 95):+.2f} dB")
    print(f"  p01/p99  = {np.percentile(_d, 1):+.2f} / {np.percentile(_d, 99):+.2f} dB")
    print()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def find_injection_site(raw_diff, rng, max_attempts=300):
    """Find a site where the diff is locally featureless.

    Criterion:
      - local std within CLEAN_RADIUS_PX < LOCAL_STD_MAX_DB
      - no pixel within CLEAN_RADIUS_PX below (global_median - PRE_EXISTING_DB)

    Returns (cy, cx, fallback_used).
    """
    h, w = raw_diff.shape
    valid = raw_diff[np.isfinite(raw_diff)]
    if valid.size < 1000:
        return None
    global_median = float(np.median(valid))
    pre_existing_thresh = global_median - PRE_EXISTING_DB

    yy, xx = np.ogrid[:h, :w]
    best_fallback = None

    for attempt in range(max_attempts):
        cy = int(rng.integers(INJECT_MARGIN_PX, h - INJECT_MARGIN_PX))
        cx = int(rng.integers(INJECT_MARGIN_PX, w - INJECT_MARGIN_PX))
        mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= CLEAN_RADIUS_PX ** 2
        local = raw_diff[mask]
        local = local[np.isfinite(local)]
        if local.size < 50:
            continue

        local_std = float(local.std())
        local_min = float(local.min())

        # Track a near-miss fallback in case strict criterion never passes
        if best_fallback is None or local_std < best_fallback[2]:
            best_fallback = (cy, cx, local_std)

        if local_std < LOCAL_STD_MAX_DB and local_min > pre_existing_thresh:
            return cy, cx, False

    if best_fallback is not None:
        return best_fallback[0], best_fallback[1], True
    return None


def apply_detector(diff, transform):
    """Apply pipeline detection. Returns (clusters, median_db)."""
    valid = diff[np.isfinite(diff)]
    if valid.size < 1000:
        return [], None
    median_db = float(np.median(valid))
    threshold = median_db - CONTRAST_DB

    dark_mask = np.isfinite(diff) & (diff < threshold)
    labeled, n_labels = ndimage.label(dark_mask, structure=np.ones((3, 3)))

    clusters = []
    for label_id in range(1, n_labels + 1):
        cluster_mask = labeled == label_id
        area = int(cluster_mask.sum())
        if area < MIN_CLUSTER_PX:
            continue
        mean_diff = float(diff[cluster_mask].mean())
        if mean_diff > (median_db - MIN_MEAN_DARK_DB):
            continue
        ys, xs = np.where(cluster_mask)
        centroid_row = float(ys.mean())
        centroid_col = float(xs.mean())
        lon, lat = rasterio.transform.xy(transform, centroid_row, centroid_col)
        clusters.append({
            "area_px": area,
            "mean_diff_db": mean_diff,
            "centroid_lat": float(lat),
            "centroid_lon": float(lon),
        })
    return clusters, median_db


def run_one(baseline_path, target_path, rng):
    with rasterio.open(baseline_path) as src:
        baseline = src.read(1).astype(np.float32)
        transform = src.transform

    with rasterio.open(target_path) as src:
        target = src.read(1).astype(np.float32)

    if baseline.shape != target.shape:
        return {"status": "shape_mismatch"}

    raw_diff = target - baseline

    site_result = find_injection_site(raw_diff, rng)
    if site_result is None:
        return {"status": "no_site"}
    cy, cx, fallback = site_result

    h, w = target.shape
    yy, xx = np.mgrid[0:h, 0:w]
    blob = np.exp(
        -(((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * INJECT_SIGMA_PX ** 2))
    ).astype(np.float32)

    injected_target = target - INJECT_AMPLITUDE_DB * blob
    injected_diff = injected_target - baseline

    clusters_after, median_db = apply_detector(injected_diff, transform)
    clusters_before, _ = apply_detector(raw_diff, transform)

    inj_lon, inj_lat = rasterio.transform.xy(transform, cy, cx)

    return {
        "status": "ok",
        "injected_lat": float(inj_lat),
        "injected_lon": float(inj_lon),
        "fallback": fallback,
        "median_db": median_db,
        "n_pre_existing": len(clusters_before),
        "n_recovered": len(clusters_after),
        "recovered_clusters": clusters_after,
    }


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
rng = np.random.default_rng(RANDOM_SEED)
results = []

for i, row in pairs.iterrows():
    iid = int(row["incident_id"])
    baseline_date = str(row["baseline_date"])
    target_date = str(row["target_date"])

    baseline_path = config.EXTRACTION_OUT / f"{iid}_{baseline_date}.tif"
    target_path = config.EXTRACTION_OUT / f"{iid}_{target_date}.tif"

    tag = f"[{i+1:2d}/{len(pairs)}] {iid} ({baseline_date} -> {target_date})"

    if not baseline_path.exists():
        print(f"{tag}: SKIP (missing baseline TIF)")
        continue
    if not target_path.exists():
        print(f"{tag}: SKIP (missing target TIF)")
        continue

    r = run_one(baseline_path, target_path, rng)

    if r["status"] != "ok":
        print(f"{tag}: SKIP ({r['status']})")
        continue

    if r["n_recovered"] == 0:
        nearest_m = None
        recovered = False
    else:
        dists = [
            geodesic(
                (r["injected_lat"], r["injected_lon"]),
                (c["centroid_lat"], c["centroid_lon"]),
            ).meters
            for c in r["recovered_clusters"]
        ]
        nearest_m = float(min(dists))
        recovered = nearest_m < RECOVERY_RADIUS_M

    results.append({
        "incident_id": iid,
        "baseline_date": baseline_date,
        "target_date": target_date,
        "injected_lat": r["injected_lat"],
        "injected_lon": r["injected_lon"],
        "fallback_used": r["fallback"],
        "n_pre_existing": r["n_pre_existing"],
        "n_recovered": r["n_recovered"],
        "nearest_recovered_m": nearest_m,
        "recovered": recovered,
    })

    status = "RECOVERED" if recovered else "MISSED"
    fb = " [fallback]" if r["fallback"] else ""
    if nearest_m is not None:
        print(f"{tag}: {status}  (nearest {nearest_m:.0f} m, "
              f"pre-existing {r['n_pre_existing']}, recovered {r['n_recovered']}){fb}")
    else:
        print(f"{tag}: {status}  (0 clusters, "
              f"pre-existing {r['n_pre_existing']}){fb}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
results_df = pd.DataFrame(results)
results_df.to_csv(RECOVERY_LOG, index=False)

print()
print("=" * 64)
print("POSITIVE CONTROL RESULTS")
print("=" * 64)

n_total = len(results_df)
if n_total == 0:
    print("No injections completed.")
    sys.exit(0)

n_recovered = int(results_df["recovered"].sum())
n_fallback = int(results_df["fallback_used"].sum())
print(f"Injections:        {n_total}  (fallback sites: {n_fallback})")
print(f"Recovered (<500m): {n_recovered}")
print(f"Detection rate:    {n_recovered / n_total:.1%}")

matched = results_df[results_df["recovered"]]
if len(matched) > 0:
    print(f"Median loc error:  {matched['nearest_recovered_m'].median():.0f} m")
    print(f"Q25/Q75 loc err:   "
          f"{matched['nearest_recovered_m'].quantile(0.25):.0f} / "
          f"{matched['nearest_recovered_m'].quantile(0.75):.0f} m")

pre = results_df["n_pre_existing"]
print()
print(f"Pre-existing clusters per image: "
      f"median {pre.median():.0f}, "
      f"Q25/Q75 {pre.quantile(0.25):.0f}/{pre.quantile(0.75):.0f}")

print()
if n_recovered / n_total >= 0.80:
    print("VERDICT: Pipeline validated. Ready to write the paper.")
elif n_recovered / n_total >= 0.50:
    print("VERDICT: Pipeline partially validated. Check the missed cases.")
else:
    print("VERDICT: Pipeline has a detection problem. Debug before writing.")

print()
print(f"Detailed results: {RECOVERY_LOG}")
