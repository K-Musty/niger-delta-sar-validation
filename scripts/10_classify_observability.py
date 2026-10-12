#!/usr/bin/env python3
"""
Phase 2e — Observability classification per acquisition.

Joins acquisition_metadata + environmental_context + habitat_group,
restricted to acquisitions that passed the QC filter in script 07.
Classifies each acquisition into one of 9 observability classes:

    OBSERVABLE_OPEN_WATER    - open-water habitat, wind 3-12, no rain
    OBSERVABLE_SWAMP         - swamp habitat, wind 3-12, no rain
    UNOBSERVABLE_TERRESTRIAL - land habitat
    UNOBSERVABLE_LOW_WIND    - wind < 3 m/s
    UNOBSERVABLE_HIGH_WIND   - wind > 12 m/s
    UNOBSERVABLE_RAIN        - precip > 5 mm/hr
    UNOBSERVABLE_NO_SAR      - no successful or QC-passing acquisitions
    UNKNOWN_HABITAT          - habitat not recorded
    UNKNOWN_ENVIRONMENT      - no ERA5 data available

Output row count = (QC-passing acquisitions) + (incidents with no QC-passing
acquisition).
"""
from __future__ import annotations

import sys
import logging
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

META_CSV  = config.DATA_INTERIM / "acquisition_metadata.csv"
ENV_CSV   = config.DATA_INTERIM / "environmental_context.csv"
INSP_CSV  = config.DATA_INTERIM / "inspection_done.csv"
DIFF_CSV  = config.DATA_INTERIM / "per_acquisition_diff.csv"
OUT_CSV   = config.DATA_INTERIM / "observability_classes.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def classify(habitat_group, wind_speed, precip):
    """
    Classification order matters: NaN checks come before numeric comparisons.
    Habitat comes first because terrestrial spills are unobservable
    regardless of wind.
    """
    # 1. Habitat-based unobservables
    if habitat_group == "land":
        return "UNOBSERVABLE_TERRESTRIAL", "Terrestrial habitat"

    if habitat_group == "unknown":
        return "UNKNOWN_HABITAT", "Habitat not recorded"

    # 2. Environment NaN check (before numeric comparisons)
    if pd.isna(wind_speed):
        return "UNKNOWN_ENVIRONMENT", "No ERA5 wind data"

    # 3. Wind thresholds
    if wind_speed < config.WIND_MIN_MS:
        return "UNOBSERVABLE_LOW_WIND", f"Wind {wind_speed:.1f} m/s < 3"

    if wind_speed > config.WIND_MAX_MS:
        return "UNOBSERVABLE_HIGH_WIND", f"Wind {wind_speed:.1f} m/s > 12"

    # 4. Rain check (guard against NaN precipitation)
    if pd.notna(precip) and precip > config.PRECIP_MAX_MM:
        return "UNOBSERVABLE_RAIN", f"Precip {precip:.1f} mm/hr"

    # 5. Observable — split by habitat quality
    if habitat_group == "open_water":
        return "OBSERVABLE_OPEN_WATER", \
               f"Open water, wind {wind_speed:.1f} m/s, precip {precip:.1f} mm"

    if habitat_group == "swamp":
        return "OBSERVABLE_SWAMP", \
               f"Swamp, wind {wind_speed:.1f} m/s, precip {precip:.1f} mm"

    # Fallback — should not be reached
    return "UNKNOWN_HABITAT", f"Unexpected habitat: {habitat_group}"


def main():
    # --- Load --------------------------------------------------------
    meta = pd.read_csv(META_CSV)
    env  = pd.read_csv(ENV_CSV)
    insp = pd.read_csv(INSP_CSV)
    diff = pd.read_csv(DIFF_CSV)

    log.info(f"Loaded {len(meta)} acquisitions, {len(env)} environment rows, "
             f"{len(insp)} inspection rows, {len(diff)} diff pairs")

    habitat_lookup = dict(zip(insp["incident_id"], insp["habitat_group"]))

    # --- Restrict to QC-passing acquisitions -------------------------
    qc_targets   = set(zip(diff["incident_id"], diff["target_date"]))
    qc_baselines = set(zip(diff["incident_id"], diff["baseline_date"]))
    qc_ok = qc_targets | qc_baselines

    meta["_pair"] = list(zip(meta["incident_id"], meta["sar_date"]))
    meta_qc = meta[meta["_pair"].isin(qc_ok)].drop(columns="_pair").copy()
    log.info(f"After QC filter: {len(meta_qc)} acquisitions "
             f"(from {len(meta)} total)")

    # --- Join metadata + environment ---------------------------------
    df = meta_qc.merge(
        env[["incident_id", "sar_date", "wind_speed", "precipitation"]],
        on=["incident_id", "sar_date"],
        how="left",
    )
    log.info(f"After merge: {len(df)} rows")

    n_missing = df["wind_speed"].isna().sum()
    if n_missing > 0:
        log.warning(f"{n_missing} rows have no ERA5 match")

    # --- Habitat lookup ----------------------------------------------
    df["habitat_group"] = df["incident_id"].map(habitat_lookup).fillna("unknown")
    n_unknown_hab = (df["habitat_group"] == "unknown").sum()
    if n_unknown_hab > 0:
        log.warning(f"{n_unknown_hab} rows have unknown habitat")

    # --- Classify each QC-passing acquisition ------------------------
    rows = []
    for _, r in df.iterrows():
        obs, reason = classify(r["habitat_group"], r["wind_speed"],
                               r["precipitation"])
        rows.append({
            "incident_id": int(r["incident_id"]),
            "sar_date": r["sar_date"],
            "habitat_group": r["habitat_group"],
            "wind_speed": r["wind_speed"],
            "precipitation": r["precipitation"],
            "observability": obs,
            "reason": reason,
        })

    # --- Add incidents with NO QC-passing acquisition ----------------
    qc_incidents = set(diff["incident_id"].unique())
    all_incidents = set(meta["incident_id"].unique())
    no_qc_incidents = sorted(all_incidents - qc_incidents)

    if no_qc_incidents:
        log.info(f"Adding {len(no_qc_incidents)} incidents with no "
                 f"QC-passing acquisition: {no_qc_incidents}")
        for iid in no_qc_incidents:
            rows.append({
                "incident_id": int(iid),
                "sar_date": None,
                "habitat_group": habitat_lookup.get(iid, "unknown"),
                "wind_speed": None,
                "precipitation": None,
                "observability": "UNOBSERVABLE_NO_SAR",
                "reason": "No successful or QC-passing Sentinel-1 acquisitions",
            })

    # --- Save --------------------------------------------------------
    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False)

    # --- Report ------------------------------------------------------
    expected = len(meta_qc) + len(no_qc_incidents)
    log.info("=" * 60)
    log.info("PHASE 2E COMPLETE")
    log.info("=" * 60)
    log.info(f"Total rows: {len(out)}  (expected {expected})")
    log.info("")
    log.info("Class distribution:")
    log.info(out["observability"].value_counts().to_string())
    log.info("")

    n_obs_water = (out["observability"] == "OBSERVABLE_OPEN_WATER").sum()
    n_obs_swamp = (out["observability"] == "OBSERVABLE_SWAMP").sum()
    n_obs_total = n_obs_water + n_obs_swamp
    n_unobs = out["observability"].str.startswith("UNOBSERVABLE").sum()
    n_unknown = out["observability"].str.startswith("UNKNOWN").sum()

    log.info(f"OBSERVABLE total:       {n_obs_total}")
    log.info(f"  - open water:         {n_obs_water}")
    log.info(f"  - swamp:              {n_obs_swamp}")
    log.info(f"Unobservable:           {n_unobs}")
    log.info(f"Unknown:                {n_unknown}")
    log.info("")
    log.info("=" * 60)
    log.info("HEADLINE NUMBER FOR PAPER")
    log.info("=" * 60)
    log.info(f"High-confidence OBSERVABLE (open water, wind 3-12, no rain): "
             f"{n_obs_water}")
    log.info(f"Total QC-passing acquisitions: {len(meta_qc)}")
    log.info(f"Incidents with no usable SAR:  {len(no_qc_incidents)}")


if __name__ == "__main__":
    main()
