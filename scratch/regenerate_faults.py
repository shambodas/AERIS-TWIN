import os
import subprocess
import pandas as pd
import json

faults = [
    'normal',
    'misfire',
    'cooling_degradation',
    'combustion_instability',
    'sensor_drift',
    'oil_pressure_degradation',
    'excessive_vibration',
    'injector_abnormality'
]

print("Generating datasets...")
dfs = []
for f in faults:
    print(f"Running simulation for {f}...")
    subprocess.run(['python', 'main.py', '--fault', f, '--duration', '1275.0'], check=True)
    csv_file = f"data/generated/aeris_twin_{f}.csv"
    
    # Check for NaNs and basic stats
    df = pd.read_csv(csv_file)
    print(f"Generated {f}: {len(df)} rows")
    dfs.append(df)

combined = pd.concat(dfs, ignore_index=True)
out_path = 'data/generated/_combined_training_dataset.csv'
combined.to_csv(out_path, index=False)
print(f"Generated {out_path} with {len(combined)} rows.")
