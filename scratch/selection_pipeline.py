import re
import json
import pandas as pd
import numpy as np

input_file = "spill-data.php.json"

try:
    print(f"Opening local archive database line pool...")
    with open(input_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
        
    df = pd.DataFrame(raw_data)
    total_raw = len(df)
    
    # 1. Clean and convert Date strings to actual Datetime objects
    df['clean_date'] = pd.to_datetime(df['incidentdate'], errors='coerce')
    df['year'] = df['clean_date'].dt.year
    
    # 2. Extract cleanly scaled numerical volume fields
    # Extracts only numeric patterns to bypass commas or text labels like '2,037 bbls'
    def parse_volume(val):
        val_str = str(val).replace(',', '').strip()
        match = re.search(r"[-+]?\d*\.\d+|\d+", val_str)
        return float(match.group()) if match else 0.0

    df['clean_volume'] = df['estimatedquantity'].apply(parse_volume)
    
    # 3. Clean spatial geometry attributes 
    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
    
    # 4. Normalize messy regulatory State labels
    # Standardizes spaced names (e.g. 'C R O S S  R I V E R') and acronym codes
    df['clean_state'] = df['statesaffected'].astype(str).str.replace(' ', '').str.upper()
    state_map = {
        'DE': 'DELTA', 'RI': 'RIVERS', 'BY': 'BAYELSA', 'AK': 'AKWA IBOM', 
        'IM': 'IMO', 'CROSSRIVER': 'CROSS RIVER', 'ON': 'ONDO', 'ED': 'EDO', 'AB': 'ABIA'
    }
    df['clean_state'] = df['clean_state'].map(state_map).fillna(df['clean_state'])

    # 5. ENFORCE YOUR CRITICAL STRATEGY BOUNDARIES
    lifespan_filter = df['year'] >= 2015
    volume_filter = df['clean_volume'] >= 50.0
    geo_filter = df['latitude'].notnull() & (df['latitude'] != 0) & df['longitude'].notnull() & (df['longitude'] != 0)
    
    working_pool = df[lifespan_filter & volume_filter & geo_filter].copy()
    
    print("\n--- FILTER METRICS BREAKDOWN ---")
    print(f"Total entries in master source file: {total_raw}")
    print(f"Real working candidates pool passing target filters: {len(working_pool)}")
    
    if len(working_pool) == 0:
        print("\nError: No records matched your threshold parameters inside this year tier.")
        exit()
        
    print("\nAvailable high-volume incidents per Niger Delta State (2015-2026):")
    print(working_pool['clean_state'].value_counts())

    # 6. SPATIAL STRATIFICATION RANDOM SAMPLING
    # Dynamically selections up to 10 random samples per active regional state grouping
    # This prevents dominant states from crowding out smaller data tiers
    stratified_sample = working_pool.groupby('clean_state', group_keys=False).apply(
        lambda x: x.sample(min(len(x), 10), random_state=42)
    )
    
    # 7. MAP STRUCTURAL METADATA TO GENERATE PILOT TRACKER SPREADSHEET
    stratified_sample['SAR_date'] = "PENDING"
    stratified_sample['visible_YN'] = "PENDING"
    stratified_sample['notes'] = ""
    
    manifest_columns = {
        'id': 'incident_id',
        'clean_state': 'state',
        'clean_date': 'date',
        'latitude': 'lat',
        'longitude': 'lon',
        'clean_volume': 'volume',
        'company': 'company',
        'cause': 'cause',
        'SAR_date': 'SAR_date',
        'visible_YN': 'visible (Y/N)',
        'notes': 'notes'
    }
    
    final_manifest = stratified_sample.rename(columns=manifest_columns)[list(manifest_columns.values())]
    
    # Format date values into standard YYYY-MM-DD strings for GEE/SAR indexing queries
    final_manifest['date'] = pd.to_datetime(final_manifest['date']).dt.strftime('%Y-%m-%d')
    
    output_filename = "nosdra_sentinel1_candidates.csv"
    final_manifest.to_csv(output_filename, index=False)
    
    print(f"\nManifest built successfully! Written {len(final_manifest)} lines to '{output_filename}'.")
    print("This file contains balanced selections cross-referencing your onshore, nearshore, and offshore indices.")

except Exception as e:
    print(f"\nExecution Pipeline Failed: {e}")

