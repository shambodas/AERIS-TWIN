#!/usr/bin/env python
"""Inspect data quality in generated CSV files."""

import pandas as pd
import numpy as np
from pathlib import Path
import json

data_dir = Path("data/generated")

# Find latest normal and fault files
csv_files = sorted(data_dir.glob("*.csv"))
if csv_files:
    latest_csv = csv_files[-1]
    print(f"Analyzing: {latest_csv.name}")
    print("=" * 100)
    
    df = pd.read_csv(latest_csv)
    
    print(f"\nDataset shape: {df.shape[0]} rows × {df.shape[1]} columns")
    print(f"Time range: {df['simulation_time_s'].min():.1f}s to {df['simulation_time_s'].max():.1f}s")
    
    # Key columns (check for both true_ and measured_ prefixes)
    key_cols = ['true_rpm', 'true_power_kw', 'true_torque_nm', 'true_cht_c', 'true_oil_temperature_c', 'fault_label']
    available_cols = [c for c in key_cols if c in df.columns]
    
    print("\n" + "=" * 100)
    print("STATISTICS")
    print("=" * 100)
    print(df[available_cols].describe().to_string())
    
    print("\n" + "=" * 100)
    print("DATA RANGES AND SANITY CHECKS")
    print("=" * 100)
    
    checks = {
        'RPM in range [800, 6000]': (df['true_rpm'].min() >= 800) and (df['true_rpm'].max() <= 6000),
        'Power positive': (df['true_power_kw'] >= 0).all(),
        'Power < 100 kW': (df['true_power_kw'] <= 100).all(),
        'Torque positive': (df['true_torque_nm'] >= 0).all(),
        'Torque < 200 Nm': (df['true_torque_nm'] <= 200).all(),
        'Temperature > 0°C': (df['true_cht_c'] > 0).all(),
        'Temperature < 150°C': (df['true_cht_c'] < 150).all(),
        'Oil temp > 0°C': (df['true_oil_temperature_c'] > 0).all(),
        'Oil temp < 120°C': (df['true_oil_temperature_c'] < 120).all(),
        'No NaN values in key cols': df[available_cols].notna().all().all(),
        'Fault labels valid [0,1,2,3,4]': set(df['fault_label'].unique()).issubset({0, 1, 2, 3, 4}),
    }
    
    for check_name, result in checks.items():
        status = "✓" if result else "✗"
        print(f"{status} {check_name}")
    
    # P = T × ω check
    omega = df['true_rpm'] * 2 * np.pi / 60
    power_check = df['true_torque_nm'] * omega / 1000  # Convert to kW
    error_pct = np.abs(power_check - df['true_power_kw']) / (df['true_power_kw'] + 1e-6) * 100
    mean_error = error_pct.mean()
    max_error = error_pct.max()
    
    print(f"\n{'=' * 100}")
    print(f"Power-Torque Verification (P = T×ω)")
    print(f"{'=' * 100}")
    print(f"Mean error: {mean_error:.4f}%")
    print(f"Max error: {max_error:.4f}%")
    print(f"Status: {'✓ PASS' if mean_error < 1.0 else '✗ FAIL'}")
    
    # Fault label distribution
    print(f"\n{'=' * 100}")
    print(f"Fault Distribution")
    print(f"{'=' * 100}")
    fault_map = {0: 'NORMAL', 1: 'MISFIRE', 2: 'COOLING', 3: 'INSTABILITY', 4: 'SENSOR'}
    for label, name in fault_map.items():
        count = (df['fault_label'] == label).sum()
        pct = count / len(df) * 100
        print(f"{name:15s}: {count:4d} records ({pct:5.1f}%)")
    
    # Summary file
    json_files = sorted(data_dir.glob("run_summary_*.json"))
    if json_files:
        with open(json_files[-1]) as f:
            summary = json.load(f)
        
        print(f"\n{'=' * 100}")
        print(f"Run Summary")
        print(f"{'=' * 100}")
        for key, value in summary.items():
            if isinstance(value, (int, float)):
                print(f"{key:30s}: {value}")

else:
    print("No CSV files found in data/generated/")
