#!/usr/bin/env python
"""
Verify physics consistency in the AERIS-TWIN dataset.
"""

import pandas as pd
import numpy as np
import math

def check_physics_consistency(csv_file):
    df = pd.read_csv(csv_file)
    
    print(f"\n{'='*80}")
    print(f"PHYSICS CONSISTENCY CHECK: {csv_file}")
    print(f"{'='*80}\n")
    
    # 1. Power = Torque × RPM (approximately)
    print("1. POWER RELATIONSHIP (P = T × ω)")
    print("-" * 80)
    
    # Convert RPM to rad/s: ω = RPM × 2π / 60
    omega = df['true_rpm'] * 2.0 * math.pi / 60.0
    
    # Calculate expected power from torque: P = T × ω
    # Note: Power should be in watts, torque in Nm
    expected_power_w = df['true_torque_nm'] * omega
    measured_power_w = df['true_power_kw'] * 1000  # Convert kW to W
    
    # Calculate relative error
    power_error = np.abs(expected_power_w - measured_power_w) / (measured_power_w + 1e-6)
    
    print(f"  Sample rows:")
    for idx in [0, 100, 500, 1000]:
        if idx < len(df):
            pe = power_error[idx] * 100
            print(f"    Row {idx:4d}: Expected={expected_power_w[idx]:12.1f}W, "
                  f"Measured={measured_power_w[idx]:12.1f}W, Error={pe:6.2f}%")
    
    avg_error = power_error.mean() * 100
    max_error = power_error.max() * 100
    print(f"\n  Average error: {avg_error:6.2f}%")
    print(f"  Maximum error: {max_error:6.2f}%")
    
    # 2. Temperature progression
    print("\n2. TEMPERATURE PROGRESSION")
    print("-" * 80)
    
    initial_oil_temp = df['true_oil_temperature_c'].iloc[0]
    final_oil_temp = df['true_oil_temperature_c'].iloc[-1]
    initial_cht = float(df['true_cht_c'].iloc[0].split('[')[1].split(',')[0])
    
    print(f"  Oil temperature: {initial_oil_temp:.1f}°C → {final_oil_temp:.1f}°C")
    print(f"  Initial CHT sample: {initial_cht:.1f}°C")
    print(f"  Temperature stabilization: {'YES' if final_oil_temp > (initial_oil_temp + 50) else 'NO'}")
    
    # 3. Pressure ranges
    print("\n3. PRESSURE RANGES")
    print("-" * 80)
    
    pressure_col = 'true_manifold_pressure_kpa'
    if pressure_col in df.columns:
        print(f"  Manifold pressure: {df[pressure_col].min():.1f} - {df[pressure_col].max():.1f} kPa")
        print(f"  Mean: {df[pressure_col].mean():.1f} kPa")
    
    if 'true_oil_pressure_psi' in df.columns:
        print(f"  Oil pressure: {df['true_oil_pressure_psi'].min():.1f} - {df['true_oil_pressure_psi'].max():.1f} psi")
        print(f"  Mean: {df['true_oil_pressure_psi'].mean():.1f} psi")
    
    # 4. Sensor noise characteristics
    print("\n4. SENSOR NOISE (True vs Measured)")
    print("-" * 80)
    
    rpm_error = np.abs(df['true_rpm'] - df['measured_rpm'])
    print(f"  RPM noise: mean={rpm_error.mean():.2f}, max={rpm_error.max():.2f}, "
          f"std={rpm_error.std():.2f}")
    
    if 'measured_oil_temperature_c' in df.columns:
        oil_temp_error = np.abs(df['true_oil_temperature_c'] - df['measured_oil_temperature_c'])
        print(f"  Oil temp noise: mean={oil_temp_error.mean():.2f}°C, max={oil_temp_error.max():.2f}°C, "
              f"std={oil_temp_error.std():.2f}°C")
    
    # 5. Vibration levels
    print("\n5. VIBRATION CHARACTERISTICS")
    print("-" * 80)
    
    print(f"  RMS: {df['true_vibration_rms'].min():.4f} - {df['true_vibration_rms'].max():.4f}")
    print(f"  Peak: {df['true_vibration_peak'].min():.4f} - {df['true_vibration_peak'].max():.4f}")
    print(f"  Mean RMS: {df['true_vibration_rms'].mean():.4f}")
    
    # 6. Fault impact on power
    if df['fault_type'].unique()[0] != 'NORMAL':
        print(f"\n6. FAULT IMPACT - {df['fault_type'].iloc[0]}")
        print("-" * 80)
        print(f"  Severity: {df['fault_severity'].iloc[0]:.2f}")
        print(f"  Power range: {df['true_power_kw'].min():.1f} - {df['true_power_kw'].max():.1f} kW")
        print(f"  Vibration RMS range: {df['true_vibration_rms'].min():.4f} - {df['true_vibration_rms'].max():.4f}")

if __name__ == "__main__":
    import glob
    
    # Find the most recent CSV files
    csv_files = glob.glob('data/generated/*.csv')
    csv_files.sort(reverse=True)
    
    for csv_file in csv_files[:3]:
        try:
            check_physics_consistency(csv_file)
        except Exception as e:
            print(f"Error processing {csv_file}: {e}")
