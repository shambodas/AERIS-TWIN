#!/usr/bin/env python
import pandas as pd

df = pd.read_csv('data/generated/aeris_twin_normal.csv')

print('SAMPLE DATA (rows 0, 100, 500, 1000):')
for idx in [0, 100, 500, 1000]:
    if idx < len(df):
        row = df.iloc[idx]
        print(f'Row {idx} (t={row["simulation_time_s"]:.1f}s):')
        print(f'  Mission: {row["mission_phase"]}')
        print(f'  True RPM: {row["true_rpm"]:.1f}, Measured: {row["measured_rpm"]:.1f}')
        print(f'  True Power: {row["true_power_kw"]:.1f} kW')
        print(f'  True Oil Temp: {row["true_oil_temperature_c"]:.1f}C')
        print()

print('Fault value distribution:')
print(df['fault_label'].value_counts().sort_index())
print()
print('Mission phase distribution:')
print(df['mission_phase'].value_counts())
