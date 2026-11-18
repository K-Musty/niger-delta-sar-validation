#!/usr/bin/env python3
"""
Sensitivity analysis: re-run anomaly detection at multiple contrast-threshold
and minimum-cluster-size combinations to verify that the spatial-mismatch
finding is robust to parameter choices.

Mirrors the main detector (scripts/08_detect_anomaly_candidates.py):
mask pixels darker than ``median - contrast_db``, label with 8-connectivity,
keep clusters of at least ``min_px`` pixels. Detection is vectorized (bincount
sizes + bincount centroids) so the full grid runs in seconds. Distances are
computed in the image plane from a precomputed reported-coordinate pixel, which
agrees with the geodesic estimate to well under 1% over the 5 km AOI.
"""
from __future__ import annotations

import sys
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import rowcol
from scipy import ndimage, stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

DIFF_CSV = config.DATA_INTERIM / "per_acquisition_diff.csv"
CAND_FLAG = config.DATA_INTERIM / "candidates_flagged.csv"
OUT_CSV  = config.DATA_OUTPUT / "sensitivity_analysis.csv"

CONTRAST_LEVELS = [3.0, 4.0, 5.0, 6.0, 7.0]
CLUSTER_LEVELS  = [50, 100, 200]

M_PER_DEG_LAT = 111320.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)


def load_all_diffs(diff_meta, coord_lookup):
    """Load all diff TIFs into memory once, precomputing per-image geometry."""
    loaded = []
    for _, rec in diff_meta.iterrows():
        iid = int(rec["incident_id"])
        diff_path = Path(rec["diff_path"])

        if not diff_path.exists() or iid not in coord_lookup:
            continue

        try:
            with rasterio.open(diff_path) as src:
                arr = src.read(1).astype(np.float32)
                transform = src.transform
                nodata = src.nodata
        except Exception:
            continue

        if nodata is not None:
            arr = np.where(arr == nodata, np.nan, arr)

        valid = np.isfinite(arr)
        if valid.sum() < 100:
            continue

        med = float(np.nanmedian(arr))
        rep_lat, rep_lon = coord_lookup[iid]

        # Reported coordinate in pixel space + meters-per-pixel for planar distance.
        r0, c0 = rowcol(transform, rep_lon, rep_lat)
        m_per_deg_lon = M_PER_DEG_LAT * np.cos(np.radians(rep_lat))
        m_per_row = abs(transform.e) * M_PER_DEG_LAT
        m_per_col = abs(transform.a) * m_per_deg_lon

        loaded.append({
            "incident_id": iid,
            "target_date": rec["target_date"],
            "pre_incident": bool(rec.get("pre_incident", False)),
            "arr": arr,
            "valid": valid,
            "median": med,
            "r0": float(r0),
            "c0": float(c0),
            "m_per_row": m_per_row,
            "m_per_col": m_per_col,
        })

    return loaded


def detect_at_threshold(loaded_diffs, contrast_db, min_px):
    """Vectorized detection at one (contrast, size) combination.

    Returns (n_post_clusters, n_ctrl_clusters, post_dist_m, ctrl_dist_m). The
    distance arrays hold the distance of every kept cluster to its reported
    coordinate, matching the per-cluster distance metric of the primary
    analysis (median over all clusters, not per-acquisition minimum).
    """
    post_dists, ctrl_dists = [], []
    structure = np.ones((3, 3), dtype=int)

    for d in loaded_diffs:
        arr = d["arr"]
        valid = d["valid"]
        med = d["median"]

        mask = (arr < (med - contrast_db)) & valid
        labels, n_clusters = ndimage.label(mask, structure=structure)

        if n_clusters == 0:
            continue

        lab = labels.ravel()
        sizes = np.bincount(lab, minlength=n_clusters + 1)

        keep = sizes >= min_px
        keep[0] = False
        kept = np.nonzero(keep)[0]

        if kept.size == 0:
            continue

        # Geometric centroids of kept clusters (single vectorized pass).
        nrows, ncols = arr.shape
        r_idx = np.repeat(np.arange(nrows, dtype=np.float64), ncols)
        c_idx = np.tile(np.arange(ncols, dtype=np.float64), nrows)
        sum_r = np.bincount(lab, weights=r_idx, minlength=n_clusters + 1)
        sum_c = np.bincount(lab, weights=c_idx, minlength=n_clusters + 1)
        rows_c = sum_r[kept] / sizes[kept]
        cols_c = sum_c[kept] / sizes[kept]

        drow = (rows_c - d["r0"]) * d["m_per_row"]
        dcol = (cols_c - d["c0"]) * d["m_per_col"]
        dist = np.hypot(drow, dcol)

        if d["pre_incident"]:
            ctrl_dists.append(dist)
        else:
            post_dists.append(dist)

    post = np.concatenate(post_dists) if post_dists else np.zeros(0)
    ctrl = np.concatenate(ctrl_dists) if ctrl_dists else np.zeros(0)
    return int(post.size), int(ctrl.size), post, ctrl


def main():
    diff_meta = pd.read_csv(DIFF_CSV)
    cand = pd.read_csv(CAND_FLAG)

    coord_lookup = {
        int(r["incident_id"]): (float(r["lat"]), float(r["lon"]))
        for _, r in cand.iterrows()
    }

    log.info(f"Loading {len(diff_meta)} diff TIFs into memory...")
    loaded = load_all_diffs(diff_meta, coord_lookup)
    log.info(f"Loaded {len(loaded)} diff images successfully")

    n_post_acq = sum(1 for d in loaded if not d["pre_incident"])
    n_ctrl_acq = sum(1 for d in loaded if d["pre_incident"])

    log.info(f"Sweeping {len(CONTRAST_LEVELS)} × {len(CLUSTER_LEVELS)} "
             f"= {len(CONTRAST_LEVELS) * len(CLUSTER_LEVELS)} combinations")

    results = []
    total = len(CONTRAST_LEVELS) * len(CLUSTER_LEVELS)
    done = 0

    for contrast_db in CONTRAST_LEVELS:
        for min_px in CLUSTER_LEVELS:
            done += 1
            log.info(f"  [{done}/{total}] contrast={contrast_db}dB, "
                     f"min_px={min_px}")

            n_post_clust, n_ctrl_clust, post_d, ctrl_d = \
                detect_at_threshold(loaded, contrast_db, min_px)

            post_rate = n_post_clust / max(n_post_acq, 1)
            ctrl_rate = n_ctrl_clust / max(n_ctrl_acq, 1)
            rate_ratio = post_rate / ctrl_rate if ctrl_rate > 0 else np.nan

            med_post = float(np.median(post_d)) if post_d.size else np.nan
            med_ctrl = float(np.median(ctrl_d)) if ctrl_d.size else np.nan

            if post_d.size > 5 and ctrl_d.size > 5:
                mw_p = float(stats.mannwhitneyu(
                    post_d, ctrl_d, alternative="two-sided").pvalue)
            else:
                mw_p = np.nan

            results.append({
                "contrast_db": contrast_db,
                "min_cluster_px": min_px,
                "post_clusters": n_post_clust,
                "ctrl_clusters": n_ctrl_clust,
                "rate_ratio": round(rate_ratio, 3) if np.isfinite(rate_ratio) else np.nan,
                "median_dist_post_m": round(med_post, 0) if np.isfinite(med_post) else np.nan,
                "median_dist_ctrl_m": round(med_ctrl, 0) if np.isfinite(med_ctrl) else np.nan,
                "mann_whitney_p": round(mw_p, 4) if np.isfinite(mw_p) else np.nan,
            })

    out = pd.DataFrame(results)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    print("\n" + "=" * 90)
    print("SENSITIVITY ANALYSIS RESULTS")
    print("=" * 90)
    print(f"\n{'Contrast':>8} {'MinPx':>6} {'Post':>6} {'Ctrl':>6} "
          f"{'RR':>6} {'Med Post':>10} {'Med Ctrl':>10} {'MW p':>8}")
    print("-" * 78)
    for _, r in out.iterrows():
        mw_str = f"{r['mann_whitney_p']:.4f}" if pd.notna(r['mann_whitney_p']) else "   N/A"
        rr_str = f"{r['rate_ratio']:.3f}" if pd.notna(r['rate_ratio']) else "  N/A"
        print(f"{r['contrast_db']:>7.0f}dB {r['min_cluster_px']:>5.0f}px "
              f"{r['post_clusters']:>6.0f} {r['ctrl_clusters']:>6.0f} "
              f"{rr_str:>6} {r['median_dist_post_m']:>9.0f}m "
              f"{r['median_dist_ctrl_m']:>9.0f}m {mw_str:>8}")

    print(f"\nSaved to {OUT_CSV}")

    valid_p = out["mann_whitney_p"].dropna()
    if len(valid_p) > 0:
        all_ns = all(valid_p > 0.05)
        print(f"\nSpatial mismatch finding: "
              f"{'STABLE across all parameters' if all_ns else 'VARIABLE — some parameters show significance'}")


if __name__ == "__main__":
    main()
