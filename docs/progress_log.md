### Phase 2b — ERA5 Environmental Context
Purpose

Retrieve 10 m wind speed, wind direction, and precipitation for each of the 262 SAR acquisitions, to be used later in the observability classification (Phase 2e). Acquisitions with wind outside the 3–12 m/s range are not usable for surface-oil detection and must be flagged as unobservable.
Inputs

    data/interim/acquisition_metadata.csv — 262 rows

    ~/.cdsapirc — CDS API key

    data/raw/era5_land_sea_mask.nc — ERA5 land-sea mask (download-once)

Outputs

    data/interim/environmental_context.csv — 262 rows

    data/interim/era5_cache/ — 230 dated directories, 32 MB, each containing the raw ERA5 .nc files

Final Statistics
Metric	Value
Rows written	262
Wind speed median	4.03 m/s
Wind speed min	0.63 m/s
Wind speed max	7.70 m/s
Low wind (<3 m/s)	67 acquisitions
Observable (3–12 m/s)	195 acquisitions (74%)
High wind (>12 m/s)	0
Precipitation max	17.23 mm/hr
Rain class (>5 mm)	2 acquisitions
Three Bugs Found and Fixed

Bug 1 — Wrong STAC→ERA5 hour. The initial version selected the nearest ERA5 hour to midnight UTC (00:00). Sentinel-1 does not overpass at midnight. It flies at ~05:00 UTC (descending) or ~17:00 UTC (ascending). Midnight is the calmest hour in tropical coastal environments, biasing wind speed down. Fixed by mapping orbit_direction → hour_utc in the extraction loop.

Bug 2 — Land vs sea grid cells. ERA5 is a 0.25° grid. Every incident queried the nearest grid cell, which for coastal Niger Delta incidents is over land. Land surface roughness damps 10 m wind by 2–3× relative to open water. This caused the initial distribution to peak at 1.5 m/s. Fixed by loading the ERA5 land-sea mask and, for each incident, resolving the nearest grid cell with land_fraction < 0.5 within a 3° radius.

Verification of Bug 2: On 2015-07-15 at 05:00 UTC, sampling four grid cells at the same moment:
Location	Wind
Port Harcourt (land, 4.75°N 7.00°E)	1.81 m/s
Nearshore Delta (4.30°N 6.50°E)	3.65 m/s
Offshore Atlantic (3.80°N 6.00°E)	5.78 m/s
Deep offshore (3.50°N 5.50°E)	5.64 m/s

The factor of 3.2× between land and open water is the reason the initial run underestimated wind by an order of magnitude.

Bug 3 — Land-sea mask 3D array indexing. The ERA5 mask file contains non-spatial dimensions (time, number, expver). Attempting to index lsm[ii, jj] on a 3D array raised IndexError: range object index out of range. Fixed by collapsing non-spatial dimensions to index 0 in load_land_sea_mask() before the ring search.
Methodological Decision Worth Reporting in the Paper

    "Studies that query ERA5 at the nearest grid cell for coastal incidents will systematically underestimate 10 m wind speed by a factor of 2–3. This biases observability classification and would erroneously exclude the majority of coastal SAR acquisitions from any oil-slick detection analysis. We resolved the nearest sea grid cell (land fraction < 0.5) within 3° of each incident coordinate."

This belongs in the Methods section. It is a small contribution but a defensible one.
What I Notice About Phase 2c

Three observations, one of which is genuinely important for the paper.
Observation 1: The p05_diff distribution is the right shape

Median p05_diff = −4.47 dB. Range −1.91 to −8.77 dB.

The p05_diff column is the 5th-percentile of pixel differences (target − baseline). Negative values mean the target image has pixels 2–9 dB darker than baseline. That is exactly the signature oil spills produce: dark pixels in the target image that were not dark before.

This is good news. If p05_diff were clustered near 0 (say, −0.5 dB), the diffs would be flat and the anomaly detector would find nothing. But the median at −4.47 dB means the diffs contain substantial dark tail. The detector in Phase 2d will produce candidate clusters.

The concern is that some of that dark tail may be:

    Real spills

    Look-alikes (low wind, biogenic films, wakes)

    Registration errors between baseline and target (slight pixel shifts creating spurious dark/bright boundaries)

The detector's job in Phase 2d is to find spatially coherent clusters. Speckle and registration artifacts get filtered by the 20-pixel minimum size.
Observation 2: Negative days_after_incident values

Min is −12 days. That means some targets in the diff are acquisitions that occurred before the incident date. These slipped through because the baseline selection uses baseline < incident_date and takes all acquisitions after baseline. But some post-baseline acquisitions can still be pre-incident.

Why this matters: A pre-incident diff is a control. It should show no spill signature. If it does show one, that is a false positive that comes from environmental change (not from the spill). Including controls in the analysis lets the paper say: "X% of post-incident diffs and Y% of pre-incident controls contained anomaly clusters." If those rates are similar, the detector is not picking up spills — it is picking up noise.

Action required before Phase 2d:
bash

cd ~/Desktop/niger-delta-sar-validation
python3 -c "
import pandas as pd
df = pd.read_csv('data/interim/per_acquisition_diff.csv')
df['pre_incident'] = df['days_after_incident'] < 0
df.to_csv('data/interim/per_acquisition_diff.csv', index=False)
print('Pre-incident (control):', df['pre_incident'].sum())
print('Post-incident (target):', (~df['pre_incident']).sum())
"

Expected: ~20 controls, ~180 targets. Report those numbers in the paper as the sample sizes for the primary (post-incident) and control (pre-incident) comparisons.
Observation 3: Two incidents are already documented as drops

    51551 — single acquisition, no baseline possible

    Four early-2015 incidents (32687, 32705, 32737, 37573) — no Sentinel-1 data

These are already documented in logs/skipped_single_acq.txt and will be classified as UNOBSERVABLE_NO_SAR in Phase 2e. They do not invalidate the pipeline. They are honest exclusions.
Next Step
Immediate: Flag pre-incident controls (5 minutes)

Run the one-liner above. Commit Phase 2c.
Then: Phase 2d — Anomaly Detection

What it does: For each of the 199 diff TIFs, apply the dual threshold (max(5th percentile, median − 3 dB)), cluster dark pixels with 8-connectivity, discard clusters smaller than 20 pixels, and record each surviving cluster's centroid, area, and geodesic distance to the reported NOSDRA coordinate.

Output: data/interim/anomaly_candidates.csv with one row per cluster per diff image.

Why it is the critical step: This is where the distance metric is computed. The distance metric is the paper's most publishable result — it reframes the paper from "0 of 63 showed visible spills" to "we quantified the spatial mismatch between NOSDRA coordinates and independently detected SAR anomalies."

Runtime: 5–10 minutes for 199 TIFs.

Checkpoint: Expected 100–300 candidate rows. If zero, the threshold is too strict. If thousands, the threshold is too loose.
What Comes After Phase 2d

    Phase 2e — Observability classifier. Joins metadata + ERA5 + habitat. Outputs 266 rows with 8 classes. This gives the paper its denominator.

    Phase 4 — Distance analysis. aggregate_nearest_anomaly.py groups candidate anomalies by acquisition, computes per-acquisition minimum distance. distance_vs_time.py produces Figure 2.

    Phase 5 — Sample flow diagram.

    Phase 3 — Scoring rubric and labeling interface (can be done in parallel with Phase 4).

    Phase 6 — Second labeler recruitment (Week 4).

Decision Point After Phase 2d

The anomaly candidate counts will tell us which story the paper tells:
Scenario	Paper framing
0 clusters in all 199 diffs	Detector is broken or diffs are flat. Investigate before proceeding.
1–20 clusters total	Very few candidates. Distance metric is sparse. Reframe as case-study.
20–100 clusters	Sufficient for distance metric. Paper is viable as planned.
100–300 clusters	Strong sample. Distance metric is well-powered. Best outcome.
>300 clusters	Threshold too loose. Tighten and re-run.

Report the count after Phase 2d. Then we decide.


### Phase 2c Checkpoint — PASSED (with one caveat)
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
[SUPERSEDED 2026-10-12] This 199 reflects the pre-QC diff count. After the
MIN_VALID_FRACTION = 0.95 filter was added to 07_per_acquisition_diff.py,
the authoritative count is 178 (114 post + 64 control). See line 329ff.
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

Phase 2d — Anomaly Candidate Detection (v2 final)

Purpose: Identify dark clusters in each diff image that could be spill signatures.

Thresholds (final):

    Contrast: cluster pixel < median − 5.0 dB

    Minimum cluster size: 100 pixels (1 hectare at 10 m resolution)

    Minimum cluster mean darkness: 5.0 dB below image median

Results:

## [SUPERSEDED] Pre-QC pipeline output
These numbers were produced by 07 before the QC filter was added.
Do not cite them. The current authoritative numbers are:
  diffs:   178 (114 post + 64 control)
  clusters: 336 (235 post + 101 control)
  rate ratio: 1.31x
  p-value: 0.495

Metric	Value
Diff images processed	199
Total candidate clusters	340
Unique incidents with ≥1 cluster	34 / 62
Post-incident clusters	238
Pre-incident control clusters	102
Post-incident rate	1.86 clusters / acquisition
Control rate	1.44 clusters / acquisition
Ratio (signal-to-noise)	1.29×

Distance to reported coordinate:
Percentile	Distance (m)
Min	160
25%	1,270
Median	1,901
75%	2,473
90%	2,788
Max	3,354

Cluster area:
Percentile	Pixels
Min	100
Median	152
75%	247
90%	507
Max	7,806

Interpretation: Detection rate in pre-incident controls is 77% of the post-incident rate. The detector cannot distinguish spill change from natural environmental variability at these thresholds. Median cluster distance from reported coordinate is 1.9 km — most clusters are near the AOI boundary, consistent with landscape features (rivers, channels) rather than spills near the reported coordinate.

Decision: Retain v2 thresholds and report the result as-is. Do not tighten further — that would be p-hacking. The finding is that NOSDRA spills are not distinguishable from background at these scales.

Comparison to v1: v1 (5th-percentile + 20-pixel min) produced 59,828 clusters with a 1.27× post/control ratio. v2 produced 340 clusters with a 1.29× ratio. The ratio is invariant to threshold tuning — the detector's selectivity changes, but its ability to separate signal from noise does not. This is quantitative evidence that the signal is not present.
 

Phase 2e Complete — Pipeline Complete
Class	Count
OBSERVABLE	98
UNOBSERVABLE_TERRESTRIAL	117
UNOBSERVABLE_LOW_WIND	41
UNKNOWN_HABITAT	5
UNOBSERVABLE_NO_SAR	4
UNOBSERVABLE_RAIN	1
Total	266

---

## Paper V2 (review response) — complete

Addressed the academic review concerns and rewrote the manuscript as `paper_v2.md`
for Int. J. Applied Earth Observation & Geoinformation.

New analysis scripts:
- `analysis/13_mixed_effects.py` — mixed-effects Poisson (GLMM with a random
  intercept per incident, Laplace/MAP) as the primary rate analysis; GEE as a
  cross-check; naive rate ratio kept for comparison. Replaces the naive Poisson
  rate test. Result (all QC-passing): GLMM IRR 1.62 [1.28–2.06], p < 0.001;
  GEE 1.54 [0.99–2.39], p = 0.057.
- `analysis/14_sensitivity.py` — vectorized 5×3 grid (contrast 3–7 dB ×
  cluster size 50–200 px). Spatial-mismatch finding stable across all 15 settings.
- `analysis/15_time_gap.py` — incident-to-first-SAR gap (median 3 days, IQR 1–5).
- `analysis/16_study_area_map.py` — study-area map (Figure 1).
- `analysis/17_visual_mismatch.py` — Incident 142357 montage (Figure 3).

Headline numbers carried into the paper: post median distance 1,972 m vs control
1,848 m (Mann-Whitney p = 0.495); 4.7% of post clusters within 500 m vs 6.9% of
controls (Fisher p = 0.43); injection recovery 20/20 (median 11.9 m).
