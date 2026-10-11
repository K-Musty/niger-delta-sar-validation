#!/usr/bin/env python3
import requests

STAC_ROOT = "https://catalogue.dataspace.copernicus.eu/stac/"
STAC_SEARCH = "https://catalogue.dataspace.copernicus.eu/stac/search"

print("=" * 60)
print("TEST 1: Can we reach the STAC catalogue root?")
print("=" * 60)
try:
    r = requests.get(STAC_ROOT, timeout=30)
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('Content-Type')}")
    print(f"Body preview: {r.text[:300]}")
except Exception as e:
    print(f"FAILED: {e}")

print()
print("=" * 60)
print("TEST 2: List available collections")
print("=" * 60)
try:
    r = requests.get(f"{STAC_ROOT}collections", timeout=30)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        cols = r.json().get("collections", [])
        print(f"Total collections: {len(cols)}")
        s1 = [c["id"] for c in cols if "s1" in c["id"].lower() or "sentinel-1" in c["id"].lower() or "sentinel1" in c["id"].lower()]
        print(f"Sentinel-1 collections: {s1}")
        if not s1:
            print("First 20 collection IDs:")
            for c in cols[:20]:
                print(f"  {c['id']}")
    else:
        print(f"Body: {r.text[:500]}")
except Exception as e:
    print(f"FAILED: {e}")

print()
print("=" * 60)
print("TEST 3: Search for Sentinel-1 over Abia State, May 2016")
print("=" * 60)
payload = {
    "collections": ["SENTINEL-1"],
    "bbox": [7.15, 4.90, 7.20, 4.95],
    "datetime": "2016-05-01T00:00:00Z/2016-05-28T23:59:59Z",
    "limit": 5,
}
try:
    r = requests.post(STAC_SEARCH, json=payload, timeout=30)
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('Content-Type')}")
    if r.status_code == 200:
        data = r.json()
        features = data.get("features", [])
        print(f"Features returned: {len(features)}")
        for f in features[:3]:
            props = f.get("properties", {})
            print(f"  ID: {f['id']}")
            print(f"    datetime: {props.get('datetime')}")
            print(f"    sar:instrument_mode: {props.get('sar:instrument_mode')}")
            print(f"    constellation: {props.get('constellation')}")
    else:
        print(f"Body: {r.text[:800]}")
except Exception as e:
    print(f"FAILED: {e}")

print()
print("=" * 60)
print("TEST 4: Search WITHOUT collection filter")
print("=" * 60)
payload = {
    "bbox": [7.15, 4.90, 7.20, 4.95],
    "datetime": "2016-05-01T00:00:00Z/2016-05-28T23:59:59Z",
    "limit": 5,
}
try:
    r = requests.post(STAC_SEARCH, json=payload, timeout=30)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        features = data.get("features", [])
        print(f"Features returned: {len(features)}")
        for f in features[:3]:
            print(f"  ID: {f['id']} | collection: {f.get('collection')}")
    else:
        print(f"Body: {r.text[:800]}")
except Exception as e:
    print(f"FAILED: {e}")
