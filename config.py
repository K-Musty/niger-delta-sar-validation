"""
config.py — Single source of truth for all paths and parameters.
Every pipeline script imports from here. No hardcoded paths elsewhere.
"""
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.resolve()
DATA_RAW     = ROOT / "data" / "raw"
DATA_INTERIM = ROOT / "data" / "interim"
DATA_OUTPUT  = ROOT / "data" / "output"
ARTIFACTS    = ROOT / "artifacts"
LOGS         = ROOT / "logs"
FIGURES      = ROOT / "figures"

EXTRACTION_OUT = ARTIFACTS / "extraction_output"
DIFF_OUT       = ARTIFACTS / "diff_output"
MONTAGE_OUT    = ARTIFACTS / "montage_pages"
ZOOM_OUT       = ARTIFACTS / "zoom_output"

# ── NOSDRA filtering ──────────────────────────────────────────────────
NOSDRA_RAW     = DATA_RAW / "spill-data.php.json"
MIN_VOLUME_BBL = 50
MIN_DATE       = "2015-01-01"
NDDC_STATES    = ["ABIA", "AKWA IBOM", "BAYELSA", "CROSS RIVER",
                  "DELTA", "EDO", "IMO", "ONDO", "RIVERS"]

# ── SAR acquisition ───────────────────────────────────────────────────
AOI_BUFFER_DEG     = 0.0225       # ~5 km × 5 km
SEARCH_WINDOW_DAYS = 14
CRS                = "EPSG:4326"
S1_COLLECTION      = "SENTINEL1_GRD"   # openEO collection name

# ── STAC (CDSE v1 — verified by probe 2026-10-11) ────────────────────
STAC_ROOT       = "https://stac.dataspace.copernicus.eu/v1"
STAC_COLLECTION = "sentinel-1-grd"
STAC_SEARCH     = f"{STAC_ROOT}/search"

# Property keys (from probe output):
#   sat:orbit_state        → "ascending" / "descending"  (NOT sar:orbit_direction)
#   sat:relative_orbit     → int
#   sar:polarizations      → list, e.g. ["VV", "VH"]
#   view:incidence_angle   → float, degrees
STAC_PROP_ORBIT_DIR   = "sat:orbit_state"
STAC_PROP_REL_ORBIT   = "sat:relative_orbit"
STAC_PROP_POLAR       = "sar:polarizations"
STAC_PROP_INCIDENCE   = "view:incidence_angle"

# ── Change detection ──────────────────────────────────────────────────
BASELINE_DAYS_BEFORE = (30, 60)
SPILL_DAYS_AFTER     = 14
ANOMALY_PERCENTILE   = 5
MIN_ANOMALY_PIXELS   = 20
MIN_VALID_FRACTION = 0.95   # reject TIFs with < 95% valid (finite) pixels
MIN_CONTRAST_DB      = 3.0        # secondary filter: cluster ≥ 3 dB darker than median

# ── Environmental context (ERA5 / CDS) ───────────────────────────────
ERA5_DATASET         = "reanalysis-era5-single-levels"
ERA5_DATASET_PRELIM  = "reanalysis-era5-single-levels-preliminary-back-extension"
ERA5_VARIABLES       = ["10m_u_component_of_wind", "10m_v_component_of_wind",
                        "total_precipitation"]
ERA5_PRELIM_CUTOFF_DAYS = 90     # use ERA5T for dates < 90 days ago

# ── Observability thresholds ──────────────────────────────────────────
WIND_MIN_MS    = 3.0     # below: whole-scene dark, slick indistinguishable
WIND_MAX_MS    = 12.0    # above: slick dispersal (literature: 10-15 m/s range)
PRECIP_MAX_MM  = 5.0     # mm/hr; ERA5 raw is meters — convert ×1000 in 06_fetch_era5.py
