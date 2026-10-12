Phase 2c Checkpoint — PASSED (with one caveat)
Metric	Value	Interpretation
Diff TIFs written	199	Good; expected 200–262
Unique incidents	62	One incident dropped (single acquisition)
Skipped (no baseline)	0	Every incident had a pre-incident acquisition
Skipped (single acq)	1	Incident 51551 had only 1 acquisition
Shape mismatches	0	All baseline/target pairs aligned cleanly
p05_diff median	−4.47 dB	Clear dark tail — anomaly detector will find clusters
p05_diff range	−8.77 to −1.91 dB	Physically plausible
days_after_incident median	+3 days	Expected
days_after_incident min	−12 days	See caveat below
The One Caveat: Negative days_after_incident

The script includes all acquisitions after the baseline, which can include acquisitions before the incident (up to 12 days before). These are pre-incident control acquisitions, not spill targets. They are useful for the paper as controls but must be flagged in downstream analysis.

Before Phase 2d, add a column to per_acquisition_diff.csv:
bash

cd ~/Desktop/niger-delta-sar-validation
python3 -c "
import pandas as pd
df = pd.read_csv('data/interim/per_acquisition_diff.csv')
df['pre_incident'] = df['days_after_incident'] < 0
df.to_csv('data/interim/per_acquisition_diff.csv', index=False)
print('Total rows:', len(df))
print('Pre-incident (control):', df['pre_incident'].sum())
print('Post-incident (target):', (~df['pre_incident']).sum())
"

Expected: ~20 pre-incident controls, ~180 post-incident targets.

Do this before running Phase 2d. The anomaly detector should process both, but downstream metrics should distinguish them.
Complete Project State (as of 2026-10-12)
Repository
text

niger-delta-sar-validation/
├── config.py                              ✅ Phase 1 complete
├── requirements.txt                       ✅
├── docs/
│   ├── methodology.md                     ✅ pipeline checklist
│   └── progress_log.md                    (this file — create it)
├── data/
│   ├── raw/
│   │   ├── spill-data.php.json            ✅ 21,167 NOSDRA records
│   │   └── era5_land_sea_mask.nc          ✅ 50 KB mask
│   ├── interim/
│   │   ├── candidates_flagged.csv         ✅ 67 incidents
│   │   ├── extraction_log.csv             ✅ 262 attempts
│   │   ├── inspection_done.csv            ✅ 67 verdicts
│   │   ├── acquisition_metadata.csv       ✅ 262 rows (Phase 2a)
│   │   ├── environmental_context.csv      ✅ 262 rows (Phase 2b)
│   │   ├── per_acquisition_diff.csv       ✅ 199 rows (Phase 2c)
│   │   └── era5_cache/                    ✅ 230 date dirs, 32 MB
│   └── output/                            (populated in later phases)
├── scripts/
│   ├── 01_clean_candidates.py             ✅ ran earlier
│   ├── 02_add_habitat.py                  ✅ ran earlier
│   ├── 03_query_acquisition_metadata.py   ✅ Phase 2a
│   ├── 04_extract_sar.py                  ✅ ran earlier
│   ├── 05_georeference.py                 ✅ ran earlier
│   ├── 05b_build_montages.py              ✅ ran earlier
│   ├── 06_fetch_era5.py                   ✅ Phase 2b (fixed)
│   └── 07_per_acquisition_diff.py         ✅ Phase 2c
├── analysis/                              (Phase 4–5)
├── figures/                               (Phase 4–5)
├── artifacts/
│   ├── extraction_output/                 ✅ 262 TIF + 262 PNG
│   ├── diff_output/                       ✅ 199 diff TIFs
│   └── montage_pages/                     ✅ 16 pages
├── logs/
│   ├── phase2b_resume.log
│   ├── phase2b_sea_wind.log
│   ├── phase2c_run.log
│   ├── skipped_no_baseline.txt            (empty)
│   ├── skipped_single_acq.txt             (51551)
│   └── skipped_shape_mismatch.txt         (empty)
└── scratch/
    ├── probe_stac.py                      ✅ validated STAC schema
    └── download_land_sea_mask.py          ✅

Key Numbers
Quantity	Value
NOSDRA raw records	21,167
Post-filter candidates	67 incidents
Incidents with SAR data	63 (4 early-2015 failures)
Unique acquisitions downloaded	230
Total acquisition rows	262
Mean acquisitions per incident	4.16
Diff TIFs produced	199
Incidents with diffs	62
Median wind (sea cell)	4.03 m/s
OBSERVABLE acquisitions (wind 3–12 m/s)	195
Key Design Decisions Made (with rationale)

    STAC property names — sat:orbit_state for orbit direction (CDSE STAC v1 schema). Verified via probe. sat:relative_orbit and sar:polarizations assumed present; check for NaN in acquisition_metadata.csv.

    Sentinel-1 overpass hour — ascending = 17:00 UTC, descending = 05:00 UTC. Used for ERA5 hour selection. Verified: descending pass at 05:00 UTC matches dawn overpass.

    ERA5 sea-cell lookup — critical correction. ERA5 10m wind over coastal land is damped by ~2–3× relative to open water. Every incident now queries the nearest grid cell with land fraction < 0.5, within a 3° radius. Confirmed on 2015-07-15: Port Harcourt 1.81 m/s vs offshore 5.78 m/s.

    ERA5 units — total_precipitation is in meters per hour. Multiplied by 1000 → mm. This was the source of an early miscalculation (max was 4.4 mm instead of 15.7 mm).

    ERA5 latency — fallback to ERA5T preliminary dataset for dates within 90 days of present. pick_dataset() handles this automatically.

    Baseline selection (Phase 2c) — baseline must be strictly pre-incident, closest to incident_date − 45 days. Targets are all acquisitions strictly after the baseline date, INCLUDING ones still pre-incident (flag these as pre_incident=True).

    Diff format — float32, LZW compression, EPSG:4326, baseline geotransform. Preserves spatial reference for downstream geolocation.

    Anomaly detection (Phase 2d, not yet run) — dual threshold: max(5th percentile, median − 3 dB). 8-connectivity clustering. Discard clusters < 20 pixels.

    Observability classification (Phase 2e, not yet run) — 8 classes. NaN checks must precede numeric comparisons. Total expected rows: 266 (262 acquisitions + 4 no-SAR incidents).

    Distance metric (Phase 4) — for each diff TIF, distance from each candidate anomaly cluster centroid to the reported NOSDRA coordinate. Report per-acquisition minimum in Figure 2.

Known Issues and Open Questions
Resolved

    ❌ STAC collection SENTINEL-1 does not exist → fixed to sentinel-1-grd

    ❌ log10() not in openeo 0.52 → fixed to log(base=10)

    ❌ NetCDF split picked crs variable → fixed to pick VV

    ❌ ERA5 wind over land (2–3× damped) → fixed via land-sea mask

    ❌ ERA5 midnight hour picked → fixed via overpass hour (5 or 17 UTC)

    ❌ Land-sea mask 3D → 2D collapse → fixed via load_land_sea_mask()

Open

    Negative days_after_incident in Phase 2c output (min −12). These are pre-incident controls, not spill targets. Flag before Phase 2d.

    Incident 51551 has only 1 acquisition → excluded from diff analysis. Document as a limitation.

    Four early-2015 incidents (32687, 32705, 32737, 37573) returned no Sentinel-1 data → will be classified UNOBSERVABLE_NO_SAR in Phase 2e.

    sat:relative_orbit and sar:polarizations — verify they are not all NaN in acquisition_metadata.csv before writing the paper. If NaN, note as a schema limitation.

Files Still to Be Written
Phase 2d — scripts/08_detect_anomaly_candidates.py

Reads diff TIFs → outputs data/interim/anomaly_candidates.csv. Uses dual threshold + 8-connectivity clustering + geodesic distance.
Phase 2e — scripts/10_classify_observability.py

Joins acquisition_metadata + environmental_context + candidates_flagged → outputs data/interim/observability_classes.csv (266 rows, 8 classes).
Phase 3 — Rubric + labeling interface

docs/scoring_rubric.md, data/interim/labeling_interface.csv.
Phase 4 — Distance analysis

analysis/aggregate_nearest_anomaly.py, analysis/distance_vs_time.py → Figure 2.
Phase 5 — Sample flow

analysis/sample_flow.py → Figure 1.
Phase 6 — Labeling

labeler_A.csv, labeler_B.csv, Cohen's κ, labeler_final.csv.
Paper Outline (working draft)

Title: Assessing the suitability of NOSDRA oil-spill incident records as ground truth for Sentinel-1 SAR-based oil-spill detection in the Niger Delta.

Central argument: NOSDRA records are event-level regulatory labels, not pixel-level ground truth. Previous studies treating NOSDRA points as validation targets measure a correspondence that does not hold. We quantify the mismatch and identify its physical and data-quality drivers.

Key results so far:

    262 Sentinel-1 acquisitions across 63 incidents extracted and georeferenced

    0 of 63 incidents showed a coherent spill signature at the reported coordinate (visual inspection)

    195 of 262 acquisitions (74%) occurred under winds suitable for oil-slick detection (3–12 m/s)

    199 per-acquisition difference images computed against strictly pre-incident baselines

    Phase 4 (distance metric) will quantify the spatial mismatch distribution


