#!/usr/bin/env python3
"""
scripts/run_pipeline.py — Run pipeline scripts and save outputs to txt.

Runs a configurable list of scripts, captures stdout + stderr, saves to
logs/runs/<timestamp>_<script>.txt, and prints a summary.

Usage:
    python scripts/run_pipeline.py              # run all default scripts
    python scripts/run_pipeline.py full         # include extraction/era5
    python scripts/run_pipeline.py 07           # only scripts matching "07"
    python scripts/run_pipeline.py validate     # only validation
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
ANALYSIS_DIR = PROJECT_ROOT / "analysis"
LOGS_DIR = PROJECT_ROOT / "logs" / "runs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Named script groups
GROUPS = {
    "validate": [
        SCRIPTS_DIR / "11_validate_detector.py",
    ],
    "core": [
        SCRIPTS_DIR / "07_per_acquisition_diff.py",
        SCRIPTS_DIR / "08_detect_anomaly_candidates.py",
        SCRIPTS_DIR / "10_classify_observability.py",
        ANALYSIS_DIR / "distance_vs_time.py",
        ANALYSIS_DIR / "sample_flow.py",
        ANALYSIS_DIR / "summary_stats.py",
    ],
    "full": [
       # SCRIPTS_DIR / "01_clean_candidates.py",
       # SCRIPTS_DIR / "02_add_habitat.py",
       # SCRIPTS_DIR / "03_query_acquisition_metadata.py",
       # SCRIPTS_DIR / "06_fetch_era5.py",
        SCRIPTS_DIR / "07_per_acquisition_diff.py",
        SCRIPTS_DIR / "08_detect_anomaly_candidates.py",
        SCRIPTS_DIR / "10_classify_observability.py",
        SCRIPTS_DIR / "11_validate_detector.py",
        ANALYSIS_DIR / "distance_vs_time.py",
        ANALYSIS_DIR / "sample_flow.py",
        ANALYSIS_DIR / "summary_stats.py",
    ],
}


def run_one(script: Path, timestamp: str) -> tuple[str, int, float, Path]:
    print(f"\n{'=' * 72}")
    print(f"Running: {script.name}")
    print(f"{'=' * 72}")
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    dt = time.time() - t0

    log_file = LOGS_DIR / f"{timestamp}_{script.stem}.txt"
    with open(log_file, "w") as f:
        f.write(f"# Script:      {script.name}\n")
        f.write(f"# Path:        {script}\n")
        f.write(f"# Run at:      {datetime.now().isoformat()}\n")
        f.write(f"# Elapsed:     {dt:.1f} s\n")
        f.write(f"# Return code: {proc.returncode}\n\n")
        f.write("## STDOUT\n")
        f.write(proc.stdout or "(empty)\n")
        if proc.stderr:
            f.write("\n## STDERR\n")
            f.write(proc.stderr)

    tail = proc.stdout[-3000:] if len(proc.stdout) > 3000 else proc.stdout
    print(tail)
    if proc.stderr:
        print("STDERR (truncated):", proc.stderr[:1500])

    status = "PASS" if proc.returncode == 0 else "FAIL"
    print(f"\n→ {status} ({dt:.1f}s) → {log_file.relative_to(PROJECT_ROOT)}")
    return script.name, status, dt, log_file


def main() -> int:
    args = sys.argv[1:]

    if not args:
        group = "core"
    elif args[0] in GROUPS:
        group = args[0]
    else:
        # filter by substring
        pattern = args[0]
        all_scripts = GROUPS["full"]
        filtered = [s for s in all_scripts if pattern in s.name]
        if not filtered:
            print(f"No scripts match '{pattern}'")
            return 1
        print(f"Filtered to {len(filtered)} scripts matching '{pattern}'")
        group = None
        scripts = filtered

    if group is not None:
        scripts = GROUPS[group]
        print(f"Running group: {group} ({len(scripts)} scripts)")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []

    for script in scripts:
        if not script.exists():
            print(f"  MISSING: {script}")
            results.append((script.name, "MISSING", 0.0, Path()))
            continue
        results.append(run_one(script, timestamp))

    print(f"\n{'=' * 72}")
    print(f"SUMMARY — group: {group or 'filter'}")
    print(f"{'=' * 72}")
    for name, status, dt, path in results:
        print(f"  {status:7s}  {name:36s}  {dt:7.1f}s")
    print(f"\nLogs in: {LOGS_DIR.relative_to(PROJECT_ROOT)}")

    return 0 if all(r[1] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
