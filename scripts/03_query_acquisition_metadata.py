#!/usr/bin/env python3
"""
03_query_acquisition_metadata.py

Query CDSE STAC v1 for acquisition metadata (orbit direction, relative orbit,
polarization, incidence angle) for every successful SAR acquisition in
extraction_log.csv.  No imagery is downloaded — only catalog metadata.

Input:  data/interim/extraction_log.csv  (262 SUCCESS rows)
        data/interim/candidates_flagged.csv  (for lat/lon, joined on incident_id)
Output: data/interim/acquisition_metadata.csv

STAC property mapping (verified by scratch/probe_stac.py, 2026-10-11):
  sat:orbit_state      → orbit_direction  (ascending / descending)
  sat:relative_orbit   → relative_orbit_number
  sar:polarizations    → polarization
  view:incidence_angle → incidence_angle
"""
import sys
import time
import pandas as pd
from pystac_client import Client
from datetime import timedelta

# ── Ensure config is importable from project root ────────────────────
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
import config

# ── Load inputs ──────────────────────────────────────────────────────
ext_log = pd.read_csv(config.DATA_INTERIM / "extraction_log.csv")
candidates = pd.read_csv(config.DATA_INTERIM / "candidates_flagged.csv")

# Filter to SUCCESS only
ext_log = ext_log[ext_log["status"] == "SUCCESS"].copy()
print(f"Loaded {len(ext_log)} successful acquisitions")

# Join lat/lon from candidates
coords = candidates[["incident_id", "lat", "lon"]].drop_duplicates(subset="incident_id")
df = ext_log.merge(coords, on="incident_id", how="left")
assert df["lat"].notna().all(), "Some incidents missing lat/lon after join!"

# ── Connect to STAC ─────────────────────────────────────────────────
client = Client.open(config.STAC_ROOT)
print(f"Connected to STAC: {config.STAC_ROOT}")
print(f"Collection: {config.STAC_COLLECTION}\n")

# ── Query each acquisition ───────────────────────────────────────────
results = []
total = len(df)

for i, row in df.iterrows():
    idx = len(results) + 1
    iid = row["incident_id"]
    sar_date = str(row["sar_date"])
    lat, lon = row["lat"], row["lon"]

    # Build search: small bbox around incident, ±1 day
    bbox_buf = 0.15  # ~15 km buffer to catch the S1 swath
    bbox = [lon - bbox_buf, lat - bbox_buf, lon + bbox_buf, lat + bbox_buf]
    dt_start = sar_date
    dt_end = str(pd.Timestamp(sar_date) + timedelta(days=1))[:10]
    datetime_range = f"{dt_start}/{dt_end}"

    try:
        search = client.search(
            collections=[config.STAC_COLLECTION],
            bbox=bbox,
            datetime=datetime_range,
            max_items=5,
        )
        items = list(search.items())
    except Exception as e:
        print(f"  [{idx}/{total}] ERROR {iid} {sar_date}: {e}")
        results.append({
            "incident_id": iid,
            "sar_date": sar_date,
            "orbit_direction": None,
            "relative_orbit_number": None,
            "polarization": None,
            "incidence_angle": None,
            "stac_item_id": None,
            "lat": lat,
            "lon": lon,
        })
        time.sleep(1)
        continue

    if not items:
        print(f"  [{idx}/{total}] NO ITEMS for {iid} {sar_date}")
        results.append({
            "incident_id": iid,
            "sar_date": sar_date,
            "orbit_direction": None,
            "relative_orbit_number": None,
            "polarization": None,
            "incidence_angle": None,
            "stac_item_id": None,
            "lat": lat,
            "lon": lon,
        })
        time.sleep(0.5)
        continue

    # Take the first matching item (closest granule)
    item = items[0]
    props = item.properties

    orbit_dir = props.get(config.STAC_PROP_ORBIT_DIR)
    rel_orbit = props.get(config.STAC_PROP_REL_ORBIT)
    polar = props.get(config.STAC_PROP_POLAR)
    incidence = props.get(config.STAC_PROP_INCIDENCE)

    # Normalize polarization list to string
    if isinstance(polar, list):
        polar = ",".join(polar)

    result = {
        "incident_id": iid,
        "sar_date": sar_date,
        "orbit_direction": orbit_dir,
        "relative_orbit_number": rel_orbit,
        "polarization": polar,
        "incidence_angle": round(incidence, 2) if incidence is not None else None,
        "stac_item_id": item.id,
        "lat": lat,
        "lon": lon,
    }
    results.append(result)

    if idx <= 3 or idx % 50 == 0:
        print(f"  [{idx}/{total}] {iid} {sar_date} → {orbit_dir}, orbit={rel_orbit}, "
              f"polar={polar}, inc={result['incidence_angle']}")

    # Rate limit: 0.5s between requests
    time.sleep(0.5)

# ── Save output ──────────────────────────────────────────────────────
out_df = pd.DataFrame(results)
out_path = config.DATA_INTERIM / "acquisition_metadata.csv"
out_df.to_csv(out_path, index=False)
print(f"\nSaved {len(out_df)} rows to {out_path}")

# ── Quick validation ─────────────────────────────────────────────────
n_orbit = out_df["orbit_direction"].notna().sum()
n_incidence = out_df["incidence_angle"].notna().sum()
n_missing = out_df["stac_item_id"].isna().sum()
print(f"\n--- Checkpoint ---")
print(f"  orbit_direction populated: {n_orbit}/{len(out_df)}")
print(f"  incidence_angle populated: {n_incidence}/{len(out_df)}")
print(f"  Missing STAC matches: {n_missing}")
if n_orbit > 0:
    print(f"  orbit_direction values: {out_df['orbit_direction'].dropna().unique()}")
if n_incidence > 0:
    inc = out_df["incidence_angle"].dropna()
    print(f"  incidence_angle range: [{inc.min()}, {inc.max()}]")
