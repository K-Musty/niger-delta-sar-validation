# Methodology

Pipeline methodology for Niger Delta SAR oil-spill validation.

## Pipeline Overview

- [x] Phase 0: Pre-flight cleanup, renumber scripts, git init
- [x] STAC probe: `scratch/probe_stac.py` — collection `sentinel-1-grd` confirmed, `sat:orbit_state` for orbit direction
- [x] Phase 1: `config.py` as single source of truth + smoke test
- [x] Phase 2a: `03_query_acquisition_metadata.py` — STAC metadata for all 262 acquisitions
- [x] Phase 2b: `06_fetch_era5.py` — wind + precipitation from ERA5/ERA5T, units in mm
- [x] Phase 2c: `07_per_acquisition_diff.py` — baseline strictly before incident, diff TIFs
- [x] Phase 2d: `08_detect_anomaly_candidates.py` — 8-connectivity, dual threshold (5 dB contrast + 100 px min)
- [x] Phase 2e: `10_classify_observability.py` — 8 classes, NaN-safe ordering, 266 rows
- [x] Phase 3: Validation — `11_validate_detector.py` synthetic positive control (19/19 recovered)
- [x] Phase 4: `analysis/distance_vs_time.py` → Figure 2
- [x] Phase 5: `analysis/sample_flow.py` → Figure 1
- [x] Phase 6: `analysis/summary_stats.py` → `data/output/stats.json`
- [x] Phase 7 (Paper V2): `analysis/13_mixed_effects.py` — GLMM primary (random intercept per incident) + GEE cross-check + naive reference; `analysis/14_sensitivity.py` — 5×3 threshold grid; `analysis/15_time_gap.py`; `analysis/16_study_area_map.py` (Figure 1); `analysis/17_visual_mismatch.py` (Figure 3). Manuscript rewritten as `paper/paper_v2.md`.

## Key Design Decisions

1. **STAC property mapping**: `sat:orbit_state` (not `sar:orbit_direction`), `sat:relative_orbit`, `sar:polarizations`, `view:incidence_angle`
2. **ERA5 units**: `total_precipitation` is in meters; multiply by 1000 before applying 5 mm threshold
3. **ERA5 latency**: Fall back to ERA5T preliminary data for acquisitions within 90 days of present
4. **Baseline selection**: Strictly pre-incident; skip incidents with no pre-incident acquisitions
5. **Clustering**: 8-connectivity (`structure=np.ones((3,3))`), dual threshold `max(p05, median - 3 dB)`
6. **Distance**: Script 08 reports all clusters (Option B); `aggregate_nearest_anomaly.py` computes per-acquisition minimum (Option A)
7. **Observability NaN safety**: `pd.isna(wind_speed)` checked before numeric comparisons
8. **CDS credentials**: `~/.cdsapirc` read automatically by `cdsapi.Client()`
