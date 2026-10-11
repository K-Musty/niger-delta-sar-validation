# Methodology

Pipeline methodology for Niger Delta SAR oil-spill validation.

## Pipeline Overview

- [x] Phase 0: Pre-flight cleanup, renumber scripts, git init
- [x] STAC probe: `scratch/probe_stac.py` — collection `sentinel-1-grd` confirmed, `sat:orbit_state` for orbit direction
- [ ] Phase 1: `config.py` as single source of truth + smoke test
- [ ] Phase 2a: `03_query_acquisition_metadata.py` — STAC metadata for all 262 acquisitions
- [ ] Phase 2b: `06_fetch_era5.py` — wind + precipitation from ERA5/ERA5T, units in mm
- [ ] Phase 2c: `07_per_acquisition_diff.py` — baseline strictly before incident, diff TIFs
- [ ] Phase 2d: `08_detect_anomaly_candidates.py` — 8-connectivity, dual threshold (p05 + 3 dB contrast)
- [ ] Phase 2e: `10_classify_observability.py` — 8 classes, NaN-safe ordering, 266 rows
- [ ] Phase 3: `docs/scoring_rubric.md` + labeling interface
- [ ] Phase 4: `analysis/aggregate_nearest_anomaly.py` + `analysis/distance_vs_time.py` → Figure 2
- [ ] Phase 5: `analysis/sample_flow.py` → Figure 1
- [ ] Phase 6: Labeling (Week 4)

## Key Design Decisions

1. **STAC property mapping**: `sat:orbit_state` (not `sar:orbit_direction`), `sat:relative_orbit`, `sar:polarizations`, `view:incidence_angle`
2. **ERA5 units**: `total_precipitation` is in meters; multiply by 1000 before applying 5 mm threshold
3. **ERA5 latency**: Fall back to ERA5T preliminary data for acquisitions within 90 days of present
4. **Baseline selection**: Strictly pre-incident; skip incidents with no pre-incident acquisitions
5. **Clustering**: 8-connectivity (`structure=np.ones((3,3))`), dual threshold `max(p05, median - 3 dB)`
6. **Distance**: Script 08 reports all clusters (Option B); `aggregate_nearest_anomaly.py` computes per-acquisition minimum (Option A)
7. **Observability NaN safety**: `pd.isna(wind_speed)` checked before numeric comparisons
8. **CDS credentials**: `~/.cdsapirc` read automatically by `cdsapi.Client()`
