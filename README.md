# Niger Delta SAR Validation

## Abstract

Systematic validation of whether National Oil Spill Detection and Response Agency (NOSDRA) incident records can serve as ground truth for Sentinel-1 Synthetic Aperture Radar (SAR) oil-spill detection in the Niger Delta, evaluated across 63 incidents and 262 Sentinel-1 acquisitions. Two complementary approaches—visual inspection of all 262 SAR image patches and automated change detection evaluating post-incident scenes against strictly pre-incident controls—both failed to distinguish post-incident acquisitions from pre-incident controls. Automated anomaly detection yielded 336 candidate dark-spot clusters across 178 difference maps with a post/control cluster rate ratio of 1.31× (p=0.495, Mann-Whitney U test), demonstrating that candidate anomalies reflect background clutter and environmental noise rather than true oil slicks. **Negative finding**: NOSDRA incident records are not suitable as pixel-level ground truth for SAR-based oil spill detection in the Niger Delta.

## Key Numbers

```text
21,167 NOSDRA records
  → 67 filtered candidates (volume ≥ 50 bbl, post-2015, NDDC state)
    → 63 incidents with Sentinel-1 coverage
      → 262 acquisitions extracted (±14-day window)
        → 178 diffs (114 post-incident + 64 pre-incident control)
          → 336 clusters (235 post-incident + 101 control)
            → 0 distinguishable spills
```

- **Post/Control Cluster Rate Ratio**: 1.31× (2.06 clusters/diff post vs. 1.58 control)
- **Distance to Reported Incident Coordinate**: Median 1,972 m (post) vs. 1,848 m (control) (*p* = 0.495, Mann–Whitney)
- **Synthetic Positive Control Recovery**: 100% (19/19 injected 8 dB synthetic anomalies recovered by detector)

## Repository Structure

```text
niger-delta-sar-validation/
├── analysis/           # Statistical analysis and figure generation scripts
├── artifacts/          # GeoTIFF differences, image montages, and detector outputs
├── data/
│   ├── raw/            # Raw NOSDRA spill database and GADM boundaries
│   ├── interim/        # Filtered candidates, STAC metadata, ERA5 environmental data
│   └── output/         # Final statistical summaries (stats.json)
├── docs/               # Data dictionary, methodology details, and progress logs
├── figures/            # Manuscript figures (sample flow, distance vs. time)
├── logs/               # Script execution logs and audit records
├── scripts/            # Numbered pipeline scripts (01–11) and orchestrator
├── config.py           # Central project configuration and shared parameters
├── requirements.txt    # Python package dependencies
└── README.md           # Project documentation
```

## Pipeline Scripts

The pipeline is orchestrated by `scripts/run_pipeline.py`, which supports running named groups (`core`, `full`, `validate`) or filtering by script name pattern.

- **`scripts/01_clean_candidates.py`**: Cleans raw NOSDRA records, assigns missing states via GADM boundary polygons, and filters to valid Niger Delta incidents (≥ 50 bbl, post-2015).
- **`scripts/02_add_habitat.py`**: Extracts and populates environmental habitat classifications (`open_water`, `swamp`, `land`) from raw NOSDRA JSON data.
- **`scripts/03_query_acquisition_metadata.py`**: Queries Copernicus Data Space Ecosystem (CDSE) STAC v1 catalog for Sentinel-1 acquisition metadata (orbit direction, relative orbit, polarizations, incidence angle).
- **`scripts/04_extract_sar.py`**: Extracts Sentinel-1 GRD spatio-temporal backscatter cubes (VV/VH, dB) via openEO over a ±14-day temporal window centered on each incident.
- **`scripts/05_georeference.py`**: Reconstructs spatial referencing (EPSG:4326) and affine geotransforms for extracted Sentinel-1 GeoTIFF patches.
- **`scripts/05b_build_montages.py`**: Generates multi-temporal visual inspection image montages for all candidate incidents.
- **`scripts/06_fetch_era5.py`**: Fetches ERA5 hourly 10 m wind components and precipitation via CDS API, using nearest sea grid cells to prevent coastal land-damping bias.
- **`scripts/07_per_acquisition_diff.py`**: Computes pixel-wise backscatter difference maps relative to strictly pre-incident baselines (30–60 days prior) for post-incident and control acquisitions.
- **`scripts/08_detect_anomaly_candidates.py`**: Detects candidate dark-spot anomaly clusters using dual-threshold 8-connectivity clustering (≥ 5 dB contrast, ≥ 100 pixels) and calculates geodesic distances.
- **`scripts/10_classify_observability.py`**: Classifies acquisitions into 9 observability regimes combining habitat type with ERA5 wind and precipitation conditions.
- **`scripts/11_validate_detector.py`**: Runs synthetic positive control experiments by injecting calibrated dark anomalies to validate detector sensitivity and recovery rate.

## Requirements

- **Python**: 3.10+
- **Python Libraries**: See `requirements.txt`
- **External API Credentials**:
  - **Copernicus Data Space Ecosystem**: Credentials configured for openEO SAR extraction and STAC API querying.
  - **ECMWF Climate Data Store (CDS)**: API key configured in `~/.cdsapirc` for ERA5 reanalysis data retrieval.

## How to Run

1. Install project dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run pipeline:
   - Run the core pipeline (change detection, anomaly detection, observability classification, and summary analysis):
     ```bash
     python scripts/run_pipeline.py
     ```
   - Run the full pipeline (including detector synthetic positive control validation):
     ```bash
     python scripts/run_pipeline.py full
     ```
   - Run a single script or pattern match:
     ```bash
     python scripts/run_pipeline.py 07
     python scripts/run_pipeline.py validate
     ```

## Data Sources

- **NOSDRA Oil Spill Database**: Raw incident database dump (`data/raw/spill-data.php.json`) from the National Oil Spill Detection and Response Agency (NOSDRA), Nigeria.
- **Sentinel-1 SAR GRD**: Level-1 Ground Range Detected C-band SAR backscatter imagery retrieved via Copernicus Data Space Ecosystem STAC API and openEO.
- **ERA5 Atmospheric Reanalysis**: Hourly 10 m wind and total precipitation datasets from ECMWF / Copernicus Climate Change Service (C3S) via the CDS API.
- **GADM Administrative Boundaries**: Nigeria administrative boundaries (`data/raw/gadm41_NGA_1.shp`) for spatial state verification.

## Citation

If you use this work, please cite:

```text
[paper in preparation]
```

## License

MIT License
