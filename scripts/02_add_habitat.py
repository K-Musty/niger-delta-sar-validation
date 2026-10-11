#!/usr/bin/env python3
"""
Populate the habitat column in inspection_template.csv
using spillareahabitat from the raw NOSDRA JSON dump.
"""

import json
import sys
from pathlib import Path
import pandas as pd

RAW = "spill-data.php.json"
TEMPLATE = "inspection_template.csv"

if not Path(RAW).exists():
    print(f"Missing: {RAW}")
    sys.exit(1)
if not Path(TEMPLATE).exists():
    print(f"Missing: {TEMPLATE}")
    print("Run make_inspection_template.py first.")
    sys.exit(1)

print(f"Loading {RAW}...")
with open(RAW, "r", encoding="utf-8") as f:
    raw = json.load(f)

if not isinstance(raw, list):
    print(f"Unexpected top-level type: {type(raw).__name__}")
    sys.exit(1)

print(f"Loaded {len(raw)} records")

# Build lookup: id -> spillareahabitat
habitat_lookup = {}
for rec in raw:
    try:
        iid = int(rec.get("id"))
    except (TypeError, ValueError):
        continue
    hab = rec.get("spillareahabitat") or ""
    habitat_lookup[iid] = str(hab).strip().lower()

print(f"Lookup built for {len(habitat_lookup)} ids")

# Apply to template
df = pd.read_csv(TEMPLATE)
df["habitat"] = df["incident_id"].map(habitat_lookup).fillna("")

filled = (df["habitat"] != "").sum()
print(f"Filled habitat for {filled} of {len(df)} rows")

# Summary of habitat codes
print()
print("Habitat code distribution in inspection template:")
print(df["habitat"].value_counts().to_string())

df.to_csv(TEMPLATE, index=False)
print()
print(f"Updated {TEMPLATE}")
print()
print("Habitat code reference (from NOSDRA):")
print("  of = offshore")
print("  sw = surface water")
print("  la = land")
print("  iw = inland water")
print("  fw = freshwater swamp")
print("  mg = mangrove")
print("  (blank) = not recorded")
