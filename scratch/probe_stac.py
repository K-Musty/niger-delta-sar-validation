#!/usr/bin/env python3
"""
Probe CDSE STAC v1 to discover:
  1. Whether 'sentinel-1-grd' is the correct collection ID
  2. Which properties are available (especially sar:*, sat:*, view:*)

Run this BEFORE writing 03_query_acquisition_metadata.py.
"""
from pystac_client import Client

STAC_URL = "https://stac.dataspace.copernicus.eu/v1"
# Use a known incident: 48354, sar_date 2016-05-05, lat~4.95, lon~7.18
BBOX = [7.15, 4.90, 7.22, 4.97]
DATETIME = "2016-05-01/2016-05-10"
COLLECTION = "sentinel-1-grd"

print(f"Probing STAC: {STAC_URL}")
print(f"Collection: {COLLECTION}")
print(f"BBOX: {BBOX}")
print(f"Datetime: {DATETIME}")
print()

try:
    client = Client.open(STAC_URL)
    search = client.search(
        collections=[COLLECTION],
        bbox=BBOX,
        datetime=DATETIME,
        max_items=3,
    )
    items = list(search.items())

    if not items:
        print("NO ITEMS RETURNED")
        print("   Collection ID or bbox may be wrong.")
        print("   Try: S1_GRD, s1-grd-cog, SENTINEL-1-GRD")
    else:
        print(f"Found {len(items)} item(s)\n")
        for item in items:
            print(f"=== Item ID: {item.id} ===")
            print(f"    Geometry type: {item.geometry['type']}")
            print(f"\n    Properties ({len(item.properties)} keys):")
            for k in sorted(item.properties.keys()):
                print(f"      {k} = {item.properties[k]}")

            # Check for the 4 critical properties
            print("\n    --- Critical property check ---")
            critical = [
                "sar:orbit_direction",
                "sat:relative_orbit",
                "sar:polarizations",
                "view:incidence_angle",
            ]
            for prop in critical:
                val = item.properties.get(prop)
                status = "FOUND" if val is not None else "MISSING"
                print(f"      {prop}: {status} = {val}")

            # Also check assets
            print(f"\n    Assets ({len(item.assets)} keys):")
            for ak in sorted(item.assets.keys()):
                a = item.assets[ak]
                print(f"      {ak}: {a.media_type} -- {a.href[:80]}...")
            print()

except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    print("\nFallback: try raw requests.post to STAC /search")
