#!/usr/bin/env python3
"""
Phase 2b — ERA5 environmental context for each SAR acquisition.

Reads wind and precipitation from ERA5 for each acquisition, using the
nearest sea grid cell (land fraction < 0.5) to the incident coordinate.
This corrects the land-damping bias that underestimates coastal wind by
a factor of 2-3x compared to open water.

Usage:
  python scripts/06_fetch_era5.py --test    # one date, ~30 s
  python scripts/06_fetch_era5.py           # full run, ~3 min if cached
"""
from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import cdsapi

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

META_CSV   = config.DATA_INTERIM / "acquisition_metadata.csv"
OUT_CSV    = config.DATA_INTERIM / "environmental_context.csv"
CACHE_DIR  = config.DATA_INTERIM / "era5_cache"
MASK_PATH  = PROJECT_ROOT / "data" / "raw" / "era5_land_sea_mask.nc"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
config.LOGS.mkdir(parents=True, exist_ok=True)

AREA = [8.5, 3.5, 4.0, 9.5]           # [N, W, S, E]
VARIABLES = list(config.ERA5_VARIABLES)
PRELIM_CUTOFF_DAYS = int(config.ERA5_PRELIM_CUTOFF_DAYS)
DS_FINAL  = config.ERA5_DATASET
DS_PRELIM = config.ERA5_DATASET_PRELIM


# ---------------------------------------------------------------------
# Dataset selection (ERA5T fallback for recent dates)
# ---------------------------------------------------------------------
def pick_dataset(sar_dt: pd.Timestamp) -> str:
    age_days = (pd.Timestamp.now(tz=None) - sar_dt).days
    return DS_PRELIM if age_days < PRELIM_CUTOFF_DAYS else DS_FINAL


# ---------------------------------------------------------------------
# Cache extraction helpers
# ---------------------------------------------------------------------
def _extract_into(src: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with open(src, "rb") as fh:
        magic = fh.read(2)
    if magic == b"PK":
        with zipfile.ZipFile(src) as zf:
            zf.extractall(dest_dir)
    else:
        shutil.move(str(src), str(dest_dir / src.name))


def fetch_one_date(client, date_str: str, dataset: str) -> Path:
    extract_dir = CACHE_DIR / date_str
    marker = extract_dir / ".ok"
    if marker.exists():
        return extract_dir
    tmp = CACHE_DIR / f"{date_str}.download"
    if tmp.exists():
        tmp.unlink()
    y, m, d = date_str.split("-")
    client.retrieve(
        dataset,
        {
            "product_type": ["reanalysis"],
            "variable": VARIABLES,
            "year":  [y],
            "month": [m],
            "day":   [d],
            "time":  [f"{h:02d}:00" for h in range(24)],
            "area":  AREA,
            "data_format": "netcdf",
            "download_format": "unarchived",
        },
        str(tmp),
    )
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    _extract_into(tmp, extract_dir)
    if tmp.exists():
        tmp.unlink()
    ncs = list(extract_dir.glob("**/*.nc"))
    if not ncs:
        raise RuntimeError(f"no .nc found in extracted {extract_dir}")
    marker.write_text(f"ok {len(ncs)} file(s)\n")
    return extract_dir


# ---------------------------------------------------------------------
# NetCDF opening + variable normalization
# ---------------------------------------------------------------------
def _norm_varnames(ds: xr.Dataset) -> xr.Dataset:
    rename = {}
    if "10m_u_component_of_wind" in ds and "u10" not in ds:
        rename["10m_u_component_of_wind"] = "u10"
    if "10m_v_component_of_wind" in ds and "v10" not in ds:
        rename["10m_v_component_of_wind"] = "v10"
    if "total_precipitation" in ds and "tp" not in ds:
        rename["total_precipitation"] = "tp"
    if "land_sea_mask" in ds and "lsm" not in ds:
        rename["land_sea_mask"] = "lsm"
    return ds.rename(rename) if rename else ds


def open_date(extract_dir: Path) -> xr.Dataset:
    ncs = sorted(extract_dir.glob("**/*.nc"))
    parts = [xr.open_dataset(f, engine="netcdf4") for f in ncs]
    try:
        ds = parts[0] if len(parts) == 1 else xr.merge(parts)
        if "valid_time" in ds.dims or "valid_time" in ds.coords:
            rename_map = {"valid_time": "time"}
            ds = ds.rename_dims(rename_map).rename_vars(rename_map)
        ds = _norm_varnames(ds)
        ds.load()
        return ds
    finally:
        for p in parts:
            try:
                p.close()
            except Exception:
                pass


def _coord_name(ds: xr.Dataset, *candidates: str) -> str:
    for c in candidates:
        if c in ds.coords or c in ds.dims or c in ds.variables:
            return c
    raise KeyError(f"none of {candidates} in dataset; have {list(ds.coords)}")


# ---------------------------------------------------------------------
# Land-sea mask: nearest sea grid cell lookup
# ---------------------------------------------------------------------
def load_land_sea_mask(path: Path):
    """
    Load the land-sea mask and collapse to a clean 2D array.
    Returns (lsm_2d_np, lats_1d_np, lons_1d_np).
    """
    ds = xr.open_dataset(path, engine="netcdf4")
    ds = _norm_varnames(ds)

    if "lsm" in ds:
        lsm = ds["lsm"]
    elif "land_sea_mask" in ds:
        lsm = ds["land_sea_mask"]
    else:
        raise KeyError(f"no land-sea variable in {list(ds.data_vars)}")

    lat_name = _coord_name(ds, "latitude", "lat")
    lon_name = _coord_name(ds, "longitude", "lon")

    # Collapse any non-spatial dimensions (time, number, expver, etc.)
    non_spatial = [d for d in lsm.dims if d not in (lat_name, lon_name)]
    if non_spatial:
        lsm = lsm.isel({d: 0 for d in non_spatial}, drop=True)

    # Ensure spatial dims are first two in the expected order
    lsm = lsm.transpose(lat_name, lon_name)

    lats = ds[lat_name].values.astype(float)
    lons = ds[lon_name].values.astype(float)
    lsm_arr = lsm.values.astype(float)

    ds.close()

    print(f"  Land-sea mask: {lsm_arr.shape} cells, "
          f"lat [{lats.min():.2f}, {lats.max():.2f}], "
          f"lon [{lons.min():.2f}, {lons.max():.2f}]")
    print(f"  Land fraction range: {np.nanmin(lsm_arr):.3f} to {np.nanmax(lsm_arr):.3f}")

    return lsm_arr, lats, lons


def find_nearest_sea_cell(lsm_arr, lats, lons,
                          lat: float, lon: float,
                          max_radius_deg: float = 3.0,
                          land_threshold: float = 0.5):
    """
    Return (sea_lat, sea_lon) of the nearest grid cell with land fraction
    < land_threshold. Expands in concentric rings.
    Returns None if none found within max_radius_deg.
    """
    i_lat = int(np.abs(lats - lat).argmin())
    i_lon = int(np.abs(lons - lon).argmin())

    # Handle descending latitude (ERA5 uses 90 -> -90)
    step_deg = abs(float(lats[1] - lats[0])) if len(lats) > 1 else 0.25
    max_rings = max(1, int(max_radius_deg / step_deg))

    # Ring 0 = the incident cell itself
    if float(lsm_arr[i_lat, i_lon]) < land_threshold:
        return float(lats[i_lat]), float(lons[i_lon])

    for radius in range(1, max_rings + 1):
        for di in range(-radius, radius + 1):
            for dj in range(-radius, radius + 1):
                if abs(di) != radius and abs(dj) != radius:
                    continue
                ii = i_lat + di
                jj = i_lon + dj
                if 0 <= ii < len(lats) and 0 <= jj < len(lons):
                    if float(lsm_arr[ii, jj]) < land_threshold:
                        return float(lats[ii]), float(lons[jj])
    return None


# ---------------------------------------------------------------------
# Point extraction from ERA5 wind dataset
# ---------------------------------------------------------------------
def extract_point(ds: xr.Dataset, when: pd.Timestamp,
                  lat: float, lon: float) -> dict:
    lat_name = _coord_name(ds, "latitude", "lat")
    lon_name = _coord_name(ds, "longitude", "lon")
    lon_q = lon if lon <= float(ds[lon_name].max()) else lon - 360.0
    pt = (ds.sel(time=when, method="nearest")
            .sel({lat_name: lat, lon_name: lon_q}, method="nearest"))
    u = float(pt["u10"].values)
    v = float(pt["v10"].values)
    p_m = float(pt["tp"].values)
    return {
        "wind_u": u,
        "wind_v": v,
        "wind_speed": float(np.hypot(u, v)),
        "precipitation": p_m * 1000.0,
    }


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    # --- Load acquisition metadata -----------------------------------
    meta = pd.read_csv(META_CSV)
    print(f"Loaded {len(meta)} acquisitions from {META_CSV}")
    meta["sar_dt"] = pd.to_datetime(meta["sar_date"], utc=True).dt.tz_localize(None)
    meta["date_str"] = meta["sar_dt"].dt.strftime("%Y-%m-%d")

    # --- Load land-sea mask ------------------------------------------
    if not MASK_PATH.exists():
        raise SystemExit(f"Missing land-sea mask: {MASK_PATH}")
    print(f"Loading land-sea mask: {MASK_PATH}")
    lsm_arr, lats, lons = load_land_sea_mask(MASK_PATH)

    # --- Resolve sea cell per incident -------------------------------
    incident_sea_cell = {}
    for iid, grp in meta.groupby("incident_id"):
        lat0 = float(grp.iloc[0]["lat"])
        lon0 = float(grp.iloc[0]["lon"])
        sea = find_nearest_sea_cell(lsm_arr, lats, lons, lat0, lon0)
        if sea is None:
            print(f"  WARNING: no sea cell within 3deg of incident {iid} "
                  f"({lat0:.3f}, {lon0:.3f}); using incident coord")
            sea = (lat0, lon0)
        incident_sea_cell[int(iid)] = sea

    print(f"Resolved sea cells for {len(incident_sea_cell)} incidents")

    # --- Unique dates ------------------------------------------------
    unique_dates = sorted(meta["date_str"].unique())
    if args.test:
        unique_dates = unique_dates[:1]
        print("[TEST MODE] processing only 1 date")
    print(f"Unique SAR dates: {len(unique_dates)}")
    print(f"Cache dir: {CACHE_DIR}\n")

    # --- Fetch loop --------------------------------------------------
    client = cdsapi.Client()
    rows: list[dict] = []

    for i, date_str in enumerate(unique_dates, 1):
        sample_dt = pd.Timestamp(date_str)
        dataset = pick_dataset(sample_dt)
        cached = (CACHE_DIR / date_str / ".ok").exists()
        tag = "cached" if cached else "fetch "
        print(f"[{i:>3}/{len(unique_dates)}] {tag} {date_str}  ({dataset})",
              end="", flush=True)
        try:
            extract_dir = fetch_one_date(client, date_str, dataset)
        except Exception as e:
            print(f"  FAILED: {type(e).__name__}: {e}")
            continue
        print("  ok")

        try:
            ds = open_date(extract_dir)
        except Exception as e:
            print(f"    open failed: {type(e).__name__}: {e}")
            continue

        for _, r in meta[meta["date_str"] == date_str].iterrows():
            try:
                orbit = str(r.get("orbit_direction", "")).lower()
                if orbit == "ascending":
                    hour_utc = 17
                elif orbit == "descending":
                    hour_utc = 5
                else:
                    hour_utc = 12

                when = pd.Timestamp(f"{r['date_str']} {hour_utc:02d}:00:00")
                sea_lat, sea_lon = incident_sea_cell[int(r["incident_id"])]

                vals = extract_point(ds, when, sea_lat, sea_lon)
            except Exception as e:
                print(f"    extract failed incident={r['incident_id']}: {e}")
                continue

            rows.append({
                "incident_id": r["incident_id"],
                "sar_date": r["sar_date"],
                **vals,
                "incident_lat": float(r["lat"]),
                "incident_lon": float(r["lon"]),
                "sea_lat": sea_lat,
                "sea_lon": sea_lon,
            })
        ds.close()

    if not rows:
        print("\nNo rows produced — nothing written.")
        return

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {len(out)} rows to {OUT_CSV}")

    # --- Checkpoint --------------------------------------------------
    print("\n--- Checkpoint ---")
    ws, pr = out["wind_speed"], out["precipitation"]
    print(f"rows:             {len(out)}  (expected ≈ {len(meta)})")
    print(f"wind_speed  min/max:  {ws.min():.3f} / {ws.max():.3f} m/s")
    print(f"wind_speed  median:   {ws.median():.3f} m/s")
    print(f"precip      min/max:  {pr.min():.4f} / {pr.max():.4f} mm")
    print(f"wind_speed < {config.WIND_MIN_MS} m/s:              "
          f"{(ws < config.WIND_MIN_MS).sum()}  (LOW_WIND)")
    print(f"wind_speed in [{config.WIND_MIN_MS}, {config.WIND_MAX_MS}] m/s:     "
          f"{((ws >= config.WIND_MIN_MS) & (ws <= config.WIND_MAX_MS)).sum()}  (OBSERVABLE)")
    print(f"wind_speed > {config.WIND_MAX_MS} m/s:             "
          f"{(ws > config.WIND_MAX_MS).sum()}  (HIGH_WIND)")
    print(f"precip > {config.PRECIP_MAX_MM} mm (RAIN class):  "
          f"{(pr > config.PRECIP_MAX_MM).sum()}")


if __name__ == "__main__":
    main()
