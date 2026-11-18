# Data Dictionary

Column-level documentation for all CSV files in `data/interim/` and `data/output/`.

---

## data/interim/candidates_flagged.csv

**67 rows** — NOSDRA incidents that survived all filters (volume ≥ 50 bbl, post-2015, NDDC state, valid coordinates). One row per incident.

| Column | Type | Description |
|---|---|---|
| `incident_id` | int | NOSDRA database primary key |
| `final_state` | str | Nigerian state (after correction) |
| `original_state` | str | State as recorded by NOSDRA |
| `assigned_state` | str | State assigned during cleaning |
| `date` | str | Incident date (YYYY-MM-DD) |
| `lat` | float | Latitude of reported spill location (EPSG:4326) |
| `lon` | float | Longitude of reported spill location (EPSG:4326) |
| `volume` | float | Estimated spill volume in barrels |
| `volume_flag` | str | Volume classification (NORMAL / HIGH) |
| `future_flag` | bool | True if incident date was in the future at time of extraction |
| `company` | str | Responsible company (e.g., SPDC, AGIP) |
| `cause` | str | Cause code (sab = sabotage, eqf = equipment failure, etc.) |
| `SAR_date` | str | Placeholder for SAR acquisition date (initially PENDING) |
| `visible (Y/N)` | str | Placeholder for visual inspection verdict (initially PENDING) |
| `notes` | str | Free-text notes |

---

## data/interim/acquisition_metadata.csv

**262 rows** — Sentinel-1 GRD acquisition metadata retrieved via CDSE STAC API. One row per (incident, acquisition) pair.

| Column | Type | Description |
|---|---|---|
| `incident_id` | int | NOSDRA incident ID (FK → candidates_flagged) |
| `sar_date` | str | SAR acquisition date (YYYY-MM-DD) |
| `orbit_direction` | str | Orbit state: "ascending" or "descending" |
| `relative_orbit_number` | int | Sentinel-1 relative orbit number |
| `polarization` | str | Polarization channels (e.g., "VV,VH") |
| `incidence_angle` | float | View incidence angle in degrees |
| `stac_item_id` | str | Full STAC item identifier |
| `lat` | float | Incident latitude (EPSG:4326) |
| `lon` | float | Incident longitude (EPSG:4326) |

---

## data/interim/environmental_context.csv

**262 rows** — ERA5 reanalysis wind and precipitation at the nearest sea grid cell for each acquisition. One row per (incident, acquisition).

| Column | Type | Description |
|---|---|---|
| `incident_id` | int | NOSDRA incident ID |
| `sar_date` | str | SAR acquisition date (YYYY-MM-DD) |
| `wind_u` | float | 10 m U-component of wind (m/s), from nearest sea grid cell |
| `wind_v` | float | 10 m V-component of wind (m/s), from nearest sea grid cell |
| `wind_speed` | float | 10 m wind speed (m/s), √(u² + v²) |
| `precipitation` | float | Total precipitation (mm/hr), converted from ERA5 meters × 1000 |
| `incident_lat` | float | Incident latitude |
| `incident_lon` | float | Incident longitude |
| `sea_lat` | float | Latitude of selected ERA5 sea grid cell (land fraction < 0.5) |
| `sea_lon` | float | Longitude of selected ERA5 sea grid cell |

---

## data/interim/extraction_log.csv

**266 rows** — Record of every SAR image extraction attempt. One row per (incident, acquisition). Includes 4 incidents with no SAR data.

| Column | Type | Description |
|---|---|---|
| `incident_id` | int | NOSDRA incident ID |
| `state` | str | Nigerian state |
| `incident_date` | str | Incident date (YYYY-MM-DD) |
| `sar_date` | str | SAR acquisition date (YYYY-MM-DD) |
| `days_after_incident` | float | Days between incident and acquisition (negative = pre-incident) |
| `status` | str | Extraction status: SUCCESS, FAILED, NO_SAR |
| `tif_file` | str | Relative path to extracted GeoTIFF |
| `png_file` | str | Relative path to quicklook PNG |
| `error` | str | Error message if status ≠ SUCCESS |

---

## data/interim/per_acquisition_diff.csv

**178 rows** — Per-acquisition difference images (target − baseline). One row per diff TIF. Authoritative count after MIN_VALID_FRACTION = 0.95 QC filter.

| Column | Type | Description |
|---|---|---|
| `incident_id` | int | NOSDRA incident ID |
| `baseline_date` | str | Baseline acquisition date (strictly pre-incident) |
| `target_date` | str | Target acquisition date |
| `diff_path` | str | Absolute path to diff GeoTIFF |
| `days_after_incident` | int | Days between incident date and target date (negative = control) |
| `baseline_days_before` | int | Days between baseline and incident date |
| `pre_incident` | bool | True if target_date < incident_date (pre-incident control) |
| `mean_diff` | float | Mean pixel difference (dB) across entire diff image |
| `min_diff` | float | Minimum pixel difference (dB) — darkest pixel |
| `p05_diff` | float | 5th percentile of pixel differences (dB) — dark tail indicator |

---

## data/interim/anomaly_candidates.csv

**336 rows** — Dark clusters detected in diff images by the v2 detector. One row per cluster. Produced by `08_detect_anomaly_candidates.py`.

| Column | Type | Description |
|---|---|---|
| `incident_id` | int | NOSDRA incident ID |
| `baseline_date` | str | Baseline date of the diff |
| `target_date` | str | Target date of the diff |
| `pre_incident` | bool | True if this diff is a pre-incident control |
| `days_after_incident` | int | Days between incident date and target date |
| `candidate_id` | int | Cluster ID within this diff image (1-indexed) |
| `centroid_lat` | float | Cluster centroid latitude (EPSG:4326) |
| `centroid_lon` | float | Cluster centroid longitude (EPSG:4326) |
| `area_pixels` | int | Cluster area in pixels (≥ 100 = 1 hectare at 10 m) |
| `mean_diff_db` | float | Mean pixel value within cluster (dB) |
| `median_image_db` | float | Image-wide median pixel value (dB) |
| `distance_from_reported_m` | float | Geodesic distance from cluster centroid to NOSDRA coordinate (m) |

---

## data/interim/observability_classes.csv

**241 rows** — Observability classification for each (incident, acquisition). One row per acquisition that could be classified.

| Column | Type | Description |
|---|---|---|
| `incident_id` | int | NOSDRA incident ID |
| `sar_date` | str | SAR acquisition date |
| `habitat_group` | str | Habitat classification: open_water, swamp, land, unknown |
| `wind_speed` | float | 10 m wind speed (m/s) |
| `precipitation` | float | Precipitation (mm/hr) |
| `observability` | str | Classification (see table below) |
| `reason` | str | Human-readable reason for classification |

**Observability classes:**

| Class | Meaning |
|---|---|
| `OBSERVABLE_OPEN_WATER` | Open water, wind 3–12 m/s, precipitation < 5 mm/hr |
| `OBSERVABLE_SWAMP` | Swamp habitat, wind 3–12 m/s, precipitation < 5 mm/hr |
| `UNOBSERVABLE_TERRESTRIAL` | Land habitat — slick not detectable over land |
| `UNOBSERVABLE_LOW_WIND` | Wind < 3 m/s — whole scene dark, slick indistinguishable |
| `UNOBSERVABLE_RAIN` | Precipitation ≥ 5 mm/hr — rain obscures surface |
| `UNOBSERVABLE_NO_SAR` | No Sentinel-1 data available for this incident |
| `UNKNOWN_HABITAT` | Habitat could not be determined |

---

## data/interim/inspection_done.csv

**67 rows** — Visual inspection results. One row per incident. Records whether a spill signature was visible in the SAR patches.

| Column | Type | Description |
|---|---|---|
| `incident_id` | int | NOSDRA incident ID |
| `final_state` | str | Nigerian state |
| `date` | str | Incident date |
| `lat` | float | Incident latitude |
| `lon` | float | Incident longitude |
| `volume` | float | Estimated volume (bbl) |
| `company` | str | Responsible company |
| `cause` | str | Cause code |
| `n_patches` | int | Number of SAR patches available |
| `habitat` | str | Habitat at reported location |
| `verdict` | str | Visual inspection verdict |
| `notes` | str | Inspector notes |
| `habitat_group` | str | Simplified habitat: open_water, swamp, land, unknown |

---

## data/interim/scored_candidates.csv

**340 rows** — Anomaly candidates with scoring criteria applied. One row per cluster. Pre-QC version (340 rows vs 336 in anomaly_candidates.csv).

| Column | Type | Description |
|---|---|---|
| `incident_id` | int | NOSDRA incident ID |
| `baseline_date` | str | Baseline date |
| `target_date` | str | Target date |
| `pre_incident` | bool | Pre-incident control flag |
| `days_after_incident` | int | Days after incident |
| `candidate_id` | int | Cluster ID within diff |
| `centroid_lat` | float | Cluster centroid latitude |
| `centroid_lon` | float | Cluster centroid longitude |
| `area_pixels` | int | Cluster area in pixels |
| `mean_diff_db` | float | Mean pixel value within cluster (dB) |
| `median_image_db` | float | Image-wide median (dB) |
| `distance_from_reported_m` | float | Distance to NOSDRA coordinate (m) |
| `c1_dark` | int | Criterion 1: cluster is sufficiently dark (0/1) |
| `c2_contiguous` | int | Criterion 2: cluster is spatially contiguous (0/1) |
| `c3_absent_from_baseline` | int | Criterion 3: cluster absent from baseline (0/1) |
| `habitat_group` | str | Habitat classification |
| `c4_water_habitat` | int | Criterion 4: cluster is over water (0/1) |
| `auto_total` | int | Sum of criteria met (0–4) |

---

## data/interim/nosdra_original_subset.csv

**100 rows** — Raw NOSDRA records subset used during early exploration. Preserves original field names from the NOSDRA JSON API.

Key columns: `id`, `incidentdate`, `estimatedquantity`, `latitude`, `longitude`, `statesaffected`, `cause`, `company`, `spillareahabitat`.

---

## data/interim/inspection_template.csv

**67 rows** — Blank template for visual inspection (same schema as inspection_done.csv). Provided for reproducibility — a second labeler would fill this in independently.

---

## data/output/stats.json

Machine-readable summary statistics. **Single source of truth** for all paper numbers. Produced by `analysis/summary_stats.py`.

Top-level keys: `sample_flow`, `cluster_counts`, `distance_m`, `close_clusters_under_500m`, `wind_ms`.
