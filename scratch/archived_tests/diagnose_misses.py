#!/usr/bin/env python3
"""
Diagnostic for the two missed injections in the positive control test.

For each miss, report:
  - The raw diff distribution and threshold
  - The injected diff distribution and threshold
  - The blob peak value and effective area above threshold
  - Whether the cluster list changed between raw and injected
  - Whether the nearest cluster to the injection moved
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage
from geopy.distance import geodesic

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

CONTRAST_DB = 5.0
MIN_CLUSTER_PX = 100
MIN_MEAN_DARK_DB = 5.0
INJECT_AMPLITUDE_DB = 8.0
INJECT_SIGMA_PX = 10

CASES = [
    (52398, "2016-10-25", "2016-11-06", 300),   # last number = fallback seed attempt
    (142357, "2018-10-03", "2018-10-10", 0),
]


def compute_clusters(diff, transform):
    valid = diff[np.isfinite(diff)]
    if valid.size < 1000:
        return [], None, None
    median_db = float(np.median(valid))
    threshold = median_db - CONTRAST_DB
    dark_mask = np.isfinite(diff) & (diff < threshold)
    labeled, n_labels = ndimage.label(dark_mask, structure=np.ones((3, 3)))
    clusters = []
    for label_id in range(1, n_labels + 1):
        m = labeled == label_id
        area = int(m.sum())
        if area < MIN_CLUSTER_PX:
            continue
        mean_diff = float(diff[m].mean())
        if mean_diff > (median_db - MIN_MEAN_DARK_DB):
            continue
        ys, xs = np.where(m)
        row, col = float(ys.mean()), float(xs.mean())
        lon, lat = rasterio.transform.xy(transform, row, col)
        clusters.append({
            "area_px": area,
            "mean_diff_db": mean_diff,
            "centroid_lat": float(lat),
            "centroid_lon": float(lon),
            "bbox": (int(ys.min()), int(xs.min()), int(ys.max()), int(xs.max())),
        })
    return clusters, median_db, threshold


def diagnose(iid, baseline_date, target_date, fallback_attempt):
    print("=" * 72)
    print(f"CASE {iid}  ({baseline_date} -> {target_date})")
    print("=" * 72)

    bp = config.EXTRACTION_OUT / f"{iid}_{baseline_date}.tif"
    tp = config.EXTRACTION_OUT / f"{iid}_{target_date}.tif"

    with rasterio.open(bp) as s:
        B = s.read(1).astype(np.float32)
        transform = s.transform
    with rasterio.open(tp) as s:
        T = s.read(1).astype(np.float32)

    print(f"Baseline shape: {B.shape}, valid: {np.isfinite(B).sum()}")
    print(f"Target   shape: {T.shape}, valid: {np.isfinite(T).sum()}")
    print()

    raw_diff = T - B
    raw_clusters, raw_median, raw_thresh = compute_clusters(raw_diff, transform)
    print(f"RAW diff:")
    print(f"  valid px:  {np.isfinite(raw_diff).sum()}")
    print(f"  median:    {raw_median:+.2f} dB")
    print(f"  threshold: {raw_thresh:+.2f} dB")
    print(f"  clusters:  {len(raw_clusters)}")

    # Pick a fallback site the same way the test did: lowest local std
    h, w = raw_diff.shape
    rng = np.random.default_rng(42)
    yy, xx = np.ogrid[:h, :w]
    margin = 80
    best = None
    for _ in range(300):
        cy = int(rng.integers(margin, h - margin))
        cx = int(rng.integers(margin, w - margin))
        mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= 15 ** 2
        local = raw_diff[mask]
        local = local[np.isfinite(local)]
        if local.size < 50:
            continue
        std = float(local.std())
        if best is None or std < best[2]:
            best = (cy, cx, std)
    cy, cx, std = best
    print(f"  fallback site: ({cy}, {cx}), local std {std:.2f} dB")

    # Report local stats at the injection site
    mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= 15 ** 2
    local = raw_diff[mask]
    local = local[np.isfinite(local)]
    print(f"  local median: {np.median(local):+.2f} dB")
    print(f"  local min:    {local.min():+.2f} dB")
    print(f"  local max:    {local.max():+.2f} dB")
    print()

    # Build blob
    blob = np.exp(-(((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * INJECT_SIGMA_PX ** 2))).astype(np.float32)
    injected_target = T - INJECT_AMPLITUDE_DB * blob
    injected_diff = injected_target - B

    # What is the peak of the injected blob in the diff?
    yy_grid, xx_grid = np.mgrid[0:h, 0:w]
    blob_mask = blob > 0.5
    peak_diff = injected_diff[cy, cx]
    raw_peak = raw_diff[cy, cx]
    print(f"Injection diagnostics:")
    print(f"  blob center row/col: ({cy}, {cx})")
    print(f"  raw diff at center:  {raw_peak:+.2f} dB")
    print(f"  injected diff at center: {peak_diff:+.2f} dB")
    print(f"  blob area > 0.5: {int(blob_mask.sum())} px")

    # Effective threshold crossing: how many pixels in blob region cross threshold?
    inj_median = float(np.median(injected_diff[np.isfinite(injected_diff)]))
    inj_thresh = inj_median - CONTRAST_DB
    crossings = int(((injected_diff < inj_thresh) & blob_mask & np.isfinite(injected_diff)).sum())
    print(f"  injected median:   {inj_median:+.2f} dB")
    print(f"  injected threshold: {inj_thresh:+.2f} dB")
    print(f"  pixels in blob below threshold: {crossings}")
    print()

    # Now what does the detector find?
    inj_clusters, _, _ = compute_clusters(injected_diff, transform)
    print(f"Injected diff clusters: {len(inj_clusters)}")
    if len(inj_clusters) > 0:
        inj_lon, inj_lat = rasterio.transform.xy(transform, cy, cx)
        dists = [
            geodesic((inj_lat, inj_lon), (c["centroid_lat"], c["centroid_lon"])).meters
            for c in inj_clusters
        ]
        nearest_idx = int(np.argmin(dists))
        print(f"  nearest to injection: {dists[nearest_idx]:.0f} m")
        print(f"  nearest cluster: {inj_clusters[nearest_idx]}")
        print(f"  its bbox: {inj_clusters[nearest_idx]['bbox']}")
        print(f"  injection center pixel: ({cy}, {cx})")
    print()


if __name__ == "__main__":
    for iid, bd, td, fb in CASES:
        diagnose(iid, bd, td, fb)
