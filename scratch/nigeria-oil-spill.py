import pandas as pd
import json

input_file = "spill-data.php.json"

with open(input_file, "r", encoding="utf-8") as f:
    raw_data = json.load(f)

df = pd.DataFrame(raw_data)

# Standardize date formats to find the real range
df['clean_date'] = pd.to_datetime(df['incidentdate'], errors='coerce')
df['year'] = df['clean_date'].dt.year

print("--- FILE TIME AUDIT ---")
print(f"Total rows in file: {len(df)}")
print(f"Earliest date found: {df['clean_date'].min()}")
print(f"Latest date found: {df['clean_date'].max()}")
print("\nRecords available per year in this specific file:")
print(df['year'].value_counts().sort_index())

