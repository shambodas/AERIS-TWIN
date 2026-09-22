import pandas as pd
import numpy as np

def compute_ols_expected(row):
    rpm = row.get("measured_rpm", 3000.0)
    throttle = row.get("true_throttle_pct", 50.0)
    altitude = row.get("true_altitude_m", 0.0)
    ambient_temp = row.get("true_ambient_temperature_c", 15.0)
    
    cht = (47.9 + 0.000765 * rpm + 0.1020 * throttle - 0.00115 * altitude + 0.632 * ambient_temp)
    raw_egt = (-12.5 + 0.0248 * rpm + 0.120 * throttle - 0.0012 * altitude + 0.450 * ambient_temp)
    egt = max(ambient_temp, raw_egt)
    oiltemp = (68.5 + 0.00165 * rpm + 0.0650 * throttle + 0.00280 * altitude + 1.21 * ambient_temp)
    return cht, egt, oiltemp

def get_measured_values(row):
    cht = max(row['measured_cht_cylinder_1_c'], row['measured_cht_cylinder_2_c'], row['measured_cht_cylinder_3_c'], row['measured_cht_cylinder_4_c'])
    egt = max(row['measured_egt_cylinder_1_c'], row['measured_egt_cylinder_2_c'], row['measured_egt_cylinder_3_c'], row['measured_egt_cylinder_4_c'])
    oiltemp = row['measured_oil_temperature_c']
    oilpress = row['measured_oil_pressure_psi']
    return cht, egt, oiltemp, oilpress

def audit():
    old_df = pd.read_csv('scratch/backup_pre_hybrid/_combined_training_dataset.csv')
    new_df = pd.read_csv('data/generated/_combined_training_dataset.csv')
    
    print("=== DATASET INTEGRITY AUDIT ===")
    print(f"Total samples: OLD={len(old_df)} -> NEW={len(new_df)}")
    print(f"NaN check: NEW NaNs={new_df.isna().sum().sum()}")
    print(f"Inf check: NEW Infs={np.isinf(new_df.select_dtypes(include=np.number)).sum().sum()}")
    
    # Check for duplicate rows
    print(f"Duplicate rows: {new_df.duplicated().sum()}")
    
    print("\n--- DISTRIBUTION ---")
    print("\nSamples per fault class (NEW):")
    print(new_df['fault_type'].value_counts().to_dict())
    print("\nSamples per severity:")
    print(new_df['fault_severity'].value_counts().to_dict())
    print("\nSamples per phase:")
    print(new_df['mission_phase'].value_counts().to_dict())
    # Note: main.py uses a single 1275s mission and default weather, so these will just reflect the generator's config
    
    print(f"\nRPM range: {new_df['measured_rpm'].min():.1f} to {new_df['measured_rpm'].max():.1f}")
    print(f"Throttle range: {new_df['true_throttle_pct'].min():.1f} to {new_df['true_throttle_pct'].max():.1f}")
    print(f"Altitude range: {new_df['true_altitude_m'].min():.1f} to {new_df['true_altitude_m'].max():.1f}")
    print(f"Ambient temp range: {new_df['true_ambient_temperature_c'].min():.1f} to {new_df['true_ambient_temperature_c'].max():.1f}")
    
    # We will compute the expected values for the old dataset using OLS,
    # and for the new dataset using RF (we can just load the RF models).
    import pickle
    with open('data/generated/expectation_training/models/rf_expected_cht.pkl', 'rb') as f:
        rf_cht = pickle.load(f)
    with open('data/generated/expectation_training/models/rf_expected_egt.pkl', 'rb') as f:
        rf_egt = pickle.load(f)
    with open('data/generated/expectation_training/models/rf_expected_oiltemp.pkl', 'rb') as f:
        rf_oilt = pickle.load(f)
        
    print("\nComputing deviations...")
    # For old dataset (OLS)
    old_cht_meas, old_egt_meas, old_oilt_meas, old_oilp_meas = [], [], [], []
    old_cht_exp, old_egt_exp, old_oilt_exp = [], [], []
    for _, row in old_df.iterrows():
        c, e, ot, op = get_measured_values(row)
        ec, ee, eot = compute_ols_expected(row)
        old_cht_meas.append(c); old_egt_meas.append(e); old_oilt_meas.append(ot)
        old_cht_exp.append(ec); old_egt_exp.append(ee); old_oilt_exp.append(eot)
        
    old_cht_dev = np.array(old_cht_meas) - np.array(old_cht_exp)
    old_egt_dev = np.array(old_egt_meas) - np.array(old_egt_exp)
    old_oilt_dev = np.array(old_oilt_meas) - np.array(old_oilt_exp)
    
    old_df['cht_dev'] = old_cht_dev
    old_df['egt_dev'] = old_egt_dev
    old_df['oiltemp_dev'] = old_oilt_dev
    
    # For new dataset (RF)
    new_cht_meas, new_egt_meas, new_oilt_meas, new_oilp_meas = [], [], [], []
    for _, row in new_df.iterrows():
        c, e, ot, op = get_measured_values(row)
        new_cht_meas.append(c); new_egt_meas.append(e); new_oilt_meas.append(ot)
        
    X_new = new_df[['measured_rpm', 'true_throttle_pct', 'true_altitude_m', 'true_ambient_temperature_c']].values
    new_cht_exp = rf_cht.predict(X_new)
    new_egt_exp = rf_egt.predict(X_new)
    new_oilt_exp = rf_oilt.predict(X_new)
    
    new_cht_dev = np.array(new_cht_meas) - new_cht_exp
    new_egt_dev = np.array(new_egt_meas) - new_egt_exp
    new_oilt_dev = np.array(new_oilt_meas) - new_oilt_exp
    
    new_df['cht_dev'] = new_cht_dev
    new_df['egt_dev'] = new_egt_dev
    new_df['oiltemp_dev'] = new_oilt_dev
    
    print("\n=== EXPECTATION-ENGINE EFFECT ANALYSIS ===")
    faults_to_check = ['NORMAL', 'COOLING_DEGRADATION', 'COMBUSTION_INSTABILITY']
    for f in faults_to_check:
        od = old_df[old_df['fault_type'] == f]
        nd = new_df[new_df['fault_type'] == f]
        if len(od) == 0 or len(nd) == 0: continue
        print(f"\nFault: {f}")
        print(f"  OLD CHT Dev: mean={od['cht_dev'].mean():.1f}, std={od['cht_dev'].std():.1f}, range=[{od['cht_dev'].min():.1f}, {od['cht_dev'].max():.1f}]")
        print(f"  NEW CHT Dev: mean={nd['cht_dev'].mean():.1f}, std={nd['cht_dev'].std():.1f}, range=[{nd['cht_dev'].min():.1f}, {nd['cht_dev'].max():.1f}]")
        print(f"  OLD EGT Dev: mean={od['egt_dev'].mean():.1f}, std={od['egt_dev'].std():.1f}, range=[{od['egt_dev'].min():.1f}, {od['egt_dev'].max():.1f}]")
        print(f"  NEW EGT Dev: mean={nd['egt_dev'].mean():.1f}, std={nd['egt_dev'].std():.1f}, range=[{nd['egt_dev'].min():.1f}, {nd['egt_dev'].max():.1f}]")
        print(f"  OLD OilT Dev: mean={od['oiltemp_dev'].mean():.1f}, std={od['oiltemp_dev'].std():.1f}, range=[{od['oiltemp_dev'].min():.1f}, {od['oiltemp_dev'].max():.1f}]")
        print(f"  NEW OilT Dev: mean={nd['oiltemp_dev'].mean():.1f}, std={nd['oiltemp_dev'].std():.1f}, range=[{nd['oiltemp_dev'].min():.1f}, {nd['oiltemp_dev'].max():.1f}]")

    print("\n=== FAULT SEPARABILITY CHECK ===")
    print("NEW mean deviations by class:")
    all_faults = ['NORMAL', 'MISFIRE', 'COOLING_DEGRADATION', 'COMBUSTION_INSTABILITY', 
                  'SENSOR_DRIFT', 'OIL_PRESSURE_DEGRADATION', 'EXCESSIVE_VIBRATION', 'INJECTOR_ABNORMALITY']
    for f in all_faults:
        sub = new_df[new_df['fault_type'] == f]
        if len(sub) == 0: continue
        print(f"  {f:<25}: CHT={sub['cht_dev'].mean():>6.1f} | EGT={sub['egt_dev'].mean():>6.1f} | OilT={sub['oiltemp_dev'].mean():>6.1f} | OilP={sub['oiltemp_dev'].mean():>6.1f}")
        
if __name__ == "__main__":
    audit()
