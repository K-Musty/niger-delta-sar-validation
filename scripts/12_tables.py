#!/usr/bin/env python3
"""
Compute final tables for the manuscript directly from CSV data.
Uses config.py for absolute paths.
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from scipy.stats import fisher_exact

# Import config for absolute paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config

# Load data using config paths
cand = pd.read_csv(config.DATA_INTERIM / 'anomaly_candidates.csv')
obs = pd.read_csv(config.DATA_INTERIM / 'observability_classes.csv')
diff = pd.read_csv(config.DATA_INTERIM / 'per_acquisition_diff.csv')

# Merge candidates with observability
cand = cand.merge(obs[['incident_id', 'sar_date', 'observability', 'habitat_group']],
                  left_on=['incident_id', 'target_date'],
                  right_on=['incident_id', 'sar_date'],
                  how='left')

# Merge diff with observability
diff = diff.merge(obs[['incident_id', 'sar_date', 'observability', 'habitat_group']],
                  left_on=['incident_id', 'target_date'],
                  right_on=['incident_id', 'sar_date'],
                  how='left')

cand['observability'] = cand['observability'].fillna('UNKNOWN_HABITAT')
diff['observability'] = diff['observability'].fillna('UNKNOWN_HABITAT')

# 1. TABLE 1: Observability counts
print("\n--- TABLE 1: Observability Classes ---")
print(obs['observability'].value_counts().to_string())

# 2. TABLE 2: Stratified Anomaly Detection
strata = [
    ('All QC-passing', diff, cand),
    ('Observable (OW+Swamp)', diff[diff['observability'].isin(['OBSERVABLE_OPEN_WATER', 'OBSERVABLE_SWAMP'])],
                              cand[cand['observability'].isin(['OBSERVABLE_OPEN_WATER', 'OBSERVABLE_SWAMP'])]),
    ('Open water only', diff[diff['observability'] == 'OBSERVABLE_OPEN_WATER'],
                        cand[cand['observability'] == 'OBSERVABLE_OPEN_WATER']),
    ('Terrestrial', diff[diff['observability'] == 'UNOBSERVABLE_TERRESTRIAL'],
                    cand[cand['observability'] == 'UNOBSERVABLE_TERRESTRIAL'])
]

print("\n--- TABLE 2: Stratified Results ---")
print(f"{'Stratum':<25} | {'Post Acq':>8} | {'Ctrl Acq':>8} | {'Post Clust':>10} | {'Ctrl Clust':>10} | {'Rate Ratio':>10} | {'Median Dist (Post/Ctrl)':>25}")
print("-" * 110)

for name, d, c in strata:
    post_acq = len(d[~d['pre_incident']])
    ctrl_acq = len(d[d['pre_incident']])
    
    post_clust = len(c[~c['pre_incident']])
    ctrl_clust = len(c[c['pre_incident']])
    
    post_rate = post_clust / post_acq if post_acq else 0
    ctrl_rate = ctrl_clust / ctrl_acq if ctrl_acq else 0
    ratio = post_rate / ctrl_rate if ctrl_rate else np.nan
    
    post_dist = c[~c['pre_incident']]['distance_from_reported_m'].median()
    ctrl_dist = c[c['pre_incident']]['distance_from_reported_m'].median()
    
    print(f"{name:<25} | {post_acq:>8} | {ctrl_acq:>8} | {post_clust:>10} | {ctrl_clust:>10} | {ratio:>10.2f} | {post_dist:>10.0f} / {ctrl_dist:<10.0f}")

# 3. FISHER EXACT TEST for Close Clusters
all_post_close = len(cand[(~cand['pre_incident']) & (cand['distance_from_reported_m'] < 500)])
all_ctrl_close = len(cand[(cand['pre_incident']) & (cand['distance_from_reported_m'] < 500)])
all_post_far = len(cand[~cand['pre_incident']]) - all_post_close
all_ctrl_far = len(cand[cand['pre_incident']]) - all_ctrl_close

odds, p = fisher_exact([[all_post_close, all_post_far], [all_ctrl_close, all_ctrl_far]])
print(f"\n--- FISHER EXACT TEST (Close Clusters < 500m) ---")
print(f"Post: {all_post_close} close, {all_post_far} far")
print(f"Ctrl: {all_ctrl_close} close, {all_ctrl_far} far")
print(f"Odds ratio: {odds:.3f}, p-value: {p:.4f}")
