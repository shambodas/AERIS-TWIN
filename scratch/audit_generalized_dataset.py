import pandas as pd
import numpy as np

def audit():
    df = pd.read_csv('data/generated/expectation_training/aeris_twin_generalized_expectations.csv')
    
    print("=== WEATHER/AMBIENT CONSISTENCY ===")
    for w in df['weather_type'].unique():
        sub = df[df['weather_type'] == w]
        # Base ambient temp would be ambient temp + 0.0065 * altitude
        base_temp = sub['true_ambient_temperature_c'] + 0.0065 * sub['true_altitude_m']
        print(f"Weather: {w}")
        print(f"  Surface/Base Temp Range: {base_temp.min():.1f}C to {base_temp.max():.1f}C")
        print(f"  Alt-Adjusted Ambient Temp Range: {sub['true_ambient_temperature_c'].min():.1f}C to {sub['true_ambient_temperature_c'].max():.1f}C")
        print(f"  Altitude Range: {sub['true_altitude_m'].min():.1f}m to {sub['true_altitude_m'].max():.1f}m")
        
    print("\n=== PHYSICAL SENSOR SANITY ===")
    sensors = {
        'CHT': 'measured_cht_cylinder_3_c', # Representative cylinder
        'EGT': 'measured_egt_cylinder_3_c',
        'Oil Temp': 'measured_oil_temperature_c',
        'Oil Pressure': 'measured_oil_pressure_psi'
    }
    
    for name, col in sensors.items():
        if col not in df.columns:
            print(f"{name} column {col} missing!")
            continue
        print(f"{name}:")
        print(f"  Min: {df[col].min():.1f}, Max: {df[col].max():.1f}, Mean: {df[col].mean():.1f}, Std: {df[col].std():.1f}")
        
        min_idx = df[col].idxmin()
        max_idx = df[col].idxmax()
        
        def trace(idx):
            r = df.iloc[idx]
            return f"[Trj: {r['trajectory_id']}, Weather: {r['weather_type']}, Alt: {r['true_altitude_m']:.0f}m, RPM: {r['true_rpm']:.0f}, Thr: {r['true_throttle_pct']:.0f}%, Phase: {r['mission_phase']}, Amb: {r['true_ambient_temperature_c']:.1f}C]"
            
        print(f"  Trace Min: {df[col].min():.1f} at {trace(min_idx)}")
        print(f"  Trace Max: {df[col].max():.1f} at {trace(max_idx)}")

    print("\n=== TRAJECTORY INDEPENDENCE ===")
    train_ids = set(df[df['split'] == 'train']['trajectory_id'])
    val_ids = set(df[df['split'] == 'val']['trajectory_id'])
    test_ids = set(df[df['split'] == 'test']['trajectory_id'])
    
    overlap = train_ids & val_ids or train_ids & test_ids or val_ids & test_ids
    print(f"Unique Trajectories per split: Train={len(train_ids)}, Val={len(val_ids)}, Test={len(test_ids)}")
    print(f"Overlap found: {bool(overlap)}")
    
    print("\n=== DISTRIBUTION CHECK ===")
    for split in ['train', 'val', 'test']:
        sub = df[df['split'] == split]
        print(f"SPLIT: {split} ({len(sub)} samples)")
        print(f"  RPM: {sub['true_rpm'].min():.1f} to {sub['true_rpm'].max():.1f}")
        print(f"  Thr: {sub['true_throttle_pct'].min():.1f} to {sub['true_throttle_pct'].max():.1f}")
        print(f"  Alt: {sub['true_altitude_m'].min():.1f} to {sub['true_altitude_m'].max():.1f}")
        print(f"  Amb: {sub['true_ambient_temperature_c'].min():.1f} to {sub['true_ambient_temperature_c'].max():.1f}")
        print(f"  CHT: {sub['measured_cht_cylinder_3_c'].min():.1f} to {sub['measured_cht_cylinder_3_c'].max():.1f}")
        print(f"  EGT: {sub['measured_egt_cylinder_3_c'].min():.1f} to {sub['measured_egt_cylinder_3_c'].max():.1f}")
        print(f"  OilT: {sub['measured_oil_temperature_c'].min():.1f} to {sub['measured_oil_temperature_c'].max():.1f}")
        print(f"  OilP: {sub['measured_oil_pressure_psi'].min():.1f} to {sub['measured_oil_pressure_psi'].max():.1f}")
        print(f"  Weather: {sub['weather_type'].value_counts().to_dict()}")
        print(f"  Phase: {sub['mission_phase'].value_counts().to_dict()}")

if __name__ == "__main__":
    audit()
