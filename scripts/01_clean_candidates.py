#!/usr/bin/env python3
"""
Consolidated cleaning pipeline for NOSDRA Sentinel-1 candidate dataset.
Author: [your name]
Date: [today]
Purpose: Assign missing states, filter to Niger Delta, flag outliers, check future dates.

Inputs:
    - nosdra_sentinel1_candidates.csv  (your 83-row candidate list)
    - gadm41_NGA_1.shp                 (GADM Nigeria state boundaries)

Outputs:
    - candidates_flagged.csv           (final cleaned candidate list)
    - clean_candidates.log             (log of all decisions)
"""

import sys
import os
import logging
from datetime import datetime

# ---------------------------------------------------------------
# Set up logging so every decision is recorded
# ---------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("clean_candidates.log", mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------
# Check dependencies before doing anything else
# ---------------------------------------------------------------
log.info("Checking dependencies...")

try:
    import pandas as pd
except ImportError:
    log.error("pandas not installed. Run: pip install pandas")
    sys.exit(1)

try:
    import geopandas as gpd
    from shapely.geometry import Point
except ImportError:
    log.error("geopandas or shapely not installed. Run: pip install geopandas shapely")
    sys.exit(1)

import numpy as np

log.info(f"pandas version: {pd.__version__}")
log.info(f"geopandas version: {gpd.__version__}")

# ---------------------------------------------------------------
# Check input files exist
# ---------------------------------------------------------------
CANDIDATES_FILE = "nosdra_sentinel1_candidates.csv"
SHAPEFILE = "gadm41_NGA_shp/gadm41_NGA_1.shp"
# If your shapefile is directly in Desktop, change the line above to:
# SHAPEFILE = "gadm41_NGA_1.shp"

if not os.path.exists(CANDIDATES_FILE):
    log.error(f"Missing input file: {CANDIDATES_FILE}")
    log.error("This should be the 83-row candidate CSV you generated earlier.")
    sys.exit(1)

if not os.path.exists(SHAPEFILE):
    log.error(f"Missing shapefile: {SHAPEFILE}")
    log.error("Download GADM Nigeria level-1 shapefile and unzip into ~/Desktop/")
    log.error("Then update the SHAPEFILE variable in this script if the path differs.")
    sys.exit(1)

# ---------------------------------------------------------------
# STEP 1: Load candidates
# ---------------------------------------------------------------
log.info("=" * 60)
log.info("STEP 1: Loading candidate records")
log.info("=" * 60)

df = pd.read_csv(CANDIDATES_FILE)
log.info(f"Loaded {len(df)} candidate records")
log.info(f"Columns: {df.columns.tolist()}")

# Validate required columns
required = ['incident_id', 'state', 'date', 'lat', 'lon', 'volume']
missing = [c for c in required if c not in df.columns]
if missing:
    log.error(f"Missing required columns: {missing}")
    sys.exit(1)

# Parse date
df['date'] = pd.to_datetime(df['date'], errors='coerce')
invalid_dates = df['date'].isna().sum()
if invalid_dates > 0:
    log.warning(f"{invalid_dates} records have unparseable dates")

# Validate coordinates
invalid_coords = df[(df['lat'].isna()) | (df['lon'].isna())].shape[0]
if invalid_coords > 0:
    log.warning(f"{invalid_coords} records have missing coordinates")
    df = df.dropna(subset=['lat', 'lon'])
    log.info(f"Dropped records with missing coordinates. Remaining: {len(df)}")

# ---------------------------------------------------------------
# STEP 2: Assign states from coordinates
# ---------------------------------------------------------------
log.info("=" * 60)
log.info("STEP 2: Assigning states from coordinates via spatial join")
log.info("=" * 60)

nigeria = gpd.read_file(SHAPEFILE)
log.info(f"Loaded shapefile with {len(nigeria)} features")
log.info(f"Shapefile columns: {nigeria.columns.tolist()}")

# Find the state name column (GADM uses NAME_1 or name_1)
name_col = None
for candidate in ['NAME_1', 'name_1', 'Name_1', 'STATE', 'state']:
    if candidate in nigeria.columns:
        name_col = candidate
        break

if name_col is None:
    log.error("Could not find state name column in shapefile.")
    log.error(f"Available columns: {nigeria.columns.tolist()}")
    sys.exit(1)

log.info(f"Using state name column: {name_col}")

# Create geometry from lat/lon
geometry = [Point(xy) for xy in zip(df['lon'], df['lat'])]
gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")

# Ensure shapefile CRS matches
if nigeria.crs != "EPSG:4326":
    log.info(f"Reprojecting shapefile from {nigeria.crs} to EPSG:4326")
    nigeria = nigeria.to_crs("EPSG:4326")

# Spatial join
joined = gpd.sjoin(gdf, nigeria[[name_col, 'geometry']], how='left', predicate='within')
joined = joined.rename(columns={name_col: 'assigned_state'})

# For records where spatial join failed, mark as UNASSIGNED
unassigned = joined['assigned_state'].isna().sum()
if unassigned > 0:
    log.warning(f"{unassigned} records could not be assigned to any state.")
    log.warning("These are likely offshore or coordinate errors.")
    log.warning(joined[joined['assigned_state'].isna()][['incident_id', 'lat', 'lon', 'state']])

# Normalize assigned_state
joined['assigned_state'] = joined['assigned_state'].str.upper().str.strip()

# Build final_state: prefer assigned_state, fall back to original state
joined['original_state'] = joined['state'].astype(str).str.upper().str.strip()
joined['final_state'] = joined['assigned_state'].fillna(joined['original_state'])

# Report disagreements between original and assigned
disagreements = joined[
    (joined['assigned_state'].notna()) &
    (joined['original_state'] != 'NAN') &
    (joined['original_state'] != joined['assigned_state'])
]
if len(disagreements) > 0:
    log.warning(f"{len(disagreements)} records have state mismatches between NOSDRA and GADM:")
    log.warning(disagreements[['incident_id', 'original_state', 'assigned_state', 'lat', 'lon']].to_string())

# Show what was fixed
fixed = joined[
    (joined['original_state'].isin(['NAN', 'NONE', ''])) |
    (joined['original_state'].isna())
]
log.info(f"Records with missing original state that were assigned: {len(fixed)}")
if len(fixed) > 0:
    log.info(fixed[['incident_id', 'lat', 'lon', 'assigned_state']].to_string())

# ---------------------------------------------------------------
# STEP 3: Filter to Niger Delta
# ---------------------------------------------------------------
log.info("=" * 60)
log.info("STEP 3: Filtering to Niger Delta states (NDDC definition)")
log.info("=" * 60)

NIGER_DELTA = [
    'ABIA', 'AKWA IBOM', 'BAYELSA', 'CROSS RIVER',
    'DELTA', 'EDO', 'IMO', 'ONDO', 'RIVERS'
]

log.info(f"Keeping states: {NIGER_DELTA}")

before = len(joined)
df_nd = joined[joined['final_state'].isin(NIGER_DELTA)].copy()
after = len(df_nd)

log.info(f"Records before filter: {before}")
log.info(f"Records after filter:  {after}")
log.info(f"Records removed:       {before - after}")

removed = joined[~joined['final_state'].isin(NIGER_DELTA)]
if len(removed) > 0:
    log.info("Removed records:")
    log.info(removed[['incident_id', 'final_state', 'date', 'volume']].to_string())

# ---------------------------------------------------------------
# STEP 4: Flag volume outliers
# ---------------------------------------------------------------
log.info("=" * 60)
log.info("STEP 4: Flagging volume outliers")
log.info("=" * 60)

# Compute stats
vol_stats = df_nd['volume'].describe()
log.info(f"Volume statistics:\n{vol_stats.to_string()}")

# Flag anything above 95th percentile OR above 2000 barrels (hard threshold)
p95 = df_nd['volume'].quantile(0.95)
df_nd['volume_flag'] = 'NORMAL'
df_nd.loc[df_nd['volume'] > p95, 'volume_flag'] = 'HIGH'
df_nd.loc[df_nd['volume'] > 2000, 'volume_flag'] = 'EXTREME'

log.info(f"95th percentile threshold: {p95:.2f} barrels")
log.info(f"HIGH flags:    {(df_nd['volume_flag'] == 'HIGH').sum()}")
log.info(f"EXTREME flags: {(df_nd['volume_flag'] == 'EXTREME').sum()}")

flagged = df_nd[df_nd['volume_flag'].isin(['HIGH', 'EXTREME'])]
if len(flagged) > 0:
    log.info("Flagged outliers (verify in news archives before keeping):")
    log.info(flagged[['incident_id', 'final_state', 'date', 'volume', 'company', 'volume_flag']].to_string())

# ---------------------------------------------------------------
# STEP 5: Check future dates
# ---------------------------------------------------------------
log.info("=" * 60)
log.info("STEP 5: Checking for future or suspicious dates")
log.info("=" * 60)

today = datetime.now()
df_nd['future_flag'] = df_nd['date'] > today

future_count = df_nd['future_flag'].sum()
if future_count > 0:
    log.warning(f"{future_count} records have dates in the future:")
    log.warning(df_nd[df_nd['future_flag']][['incident_id', 'final_state', 'date', 'volume']].to_string())
else:
    log.info("No future-dated records found.")

# Also flag records within last 30 days (may not have SAR yet)
recent = df_nd[df_nd['date'] > (today - pd.Timedelta(days=30))]
if len(recent) > 0:
    log.info(f"{len(recent)} records from the last 30 days (SAR may not be processed yet):")
    log.info(recent[['incident_id', 'final_state', 'date']].to_string())

# ---------------------------------------------------------------
# STEP 6: Save final output
# ---------------------------------------------------------------
log.info("=" * 60)
log.info("STEP 6: Saving cleaned output")
log.info("=" * 60)

# Drop geometry column before saving to CSV
output = df_nd.drop(columns=['geometry'], errors='ignore')

# Reorder columns for readability
preferred_order = [
    'incident_id', 'final_state', 'original_state', 'assigned_state',
    'date', 'lat', 'lon', 'volume', 'volume_flag', 'future_flag',
    'company', 'cause', 'SAR_date', 'visible (Y/N)', 'notes'
]
existing = [c for c in preferred_order if c in output.columns]
other = [c for c in output.columns if c not in existing]
output = output[existing + other]

output.to_csv("candidates_flagged.csv", index=False)

log.info(f"Saved {len(output)} records to candidates_flagged.csv")
log.info("=" * 60)
log.info("PIPELINE COMPLETE")
log.info("=" * 60)
log.info("")
log.info("Next steps:")
log.info("1. Open candidates_flagged.csv in a spreadsheet.")
log.info("2. Manually verify all records flagged as HIGH or EXTREME volume")
log.info("   by searching news archives (e.g., 'Eroton oil spill 2022').")
log.info("3. For any record you cannot verify, add a note in the 'notes' column")
log.info("   such as 'volume unverified'. Do NOT delete.")
log.info("4. Then run the SAR visibility pilot on the first 10 records.")
log.info("")
log.info(f"Log written to clean_candidates.log")
