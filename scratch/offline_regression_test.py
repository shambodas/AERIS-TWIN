import pandas as pd
import numpy as np
import sys
from sklearn.metrics import mean_absolute_error

sys.path.insert(0, '.')
from intelligence.physics_expectation import PhysicsExpectationEngine

def main():
    df = pd.read_csv('data/generated/expectation_training/aeris_twin_generalized_expectations.csv')
    test_df = df[df['split'] == 'test']
    
    engine = PhysicsExpectationEngine()
    
    preds_cht, preds_egt, preds_oilt, preds_oilp = [], [], [], []
    
    print(f"Testing {len(test_df)} samples...")
    # Batch predict instead of row-by-row for the offline test speed
    X = test_df[['true_rpm', 'true_throttle_pct', 'true_altitude_m', 'true_ambient_temperature_c']].values
    
    if engine.rf_models['cht']:
        preds_cht = engine.rf_models['cht'].predict(X)
    if engine.rf_models['egt']:
        preds_egt = engine.rf_models['egt'].predict(X)
    if engine.rf_models['oiltemp']:
        preds_oilt = engine.rf_models['oiltemp'].predict(X)
        
    # Temporarily remove RF models to bypass slow single-row prediction in the loop
    original_models = engine.rf_models
    engine.rf_models = {'cht': None, 'egt': None, 'oiltemp': None}
        
    for idx, row in test_df.iterrows():
        # Predict oil pressure using the engine's original logic row-by-row (since it's just math, it's fast)
        exp = engine.calculate({
            'rpm': row['true_rpm'],
            'throttle_pct': row['true_throttle_pct'],
            'altitude_m': row['true_altitude_m'],
            'ambient_temperature_c': row['true_ambient_temperature_c'],
            'oil_temperature_c': row['measured_oil_temperature_c']
        })
        preds_oilp.append(exp['expected_oil_pressure'])
        
    engine.rf_models = original_models
        
    mae_cht = mean_absolute_error(test_df['measured_cht_cylinder_3_c'], preds_cht)
    mae_egt = mean_absolute_error(test_df['measured_egt_cylinder_3_c'], preds_egt)
    mae_oilt = mean_absolute_error(test_df['measured_oil_temperature_c'], preds_oilt)
    mae_oilp = mean_absolute_error(test_df['measured_oil_pressure_psi'], preds_oilp)
    
    print("\n=== INTEGRATION TEST (11 TEST TRAJECTORIES) ===")
    print(f"CHT MAE:      {mae_cht:.2f}")
    print(f"EGT MAE:      {mae_egt:.2f}")
    print(f"OilTemp MAE:  {mae_oilt:.2f}")
    print(f"OilPress MAE: {mae_oilp:.2f}")
    
    print("\n=== HIGH-ALTITUDE DIAGNOSTIC ===")
    mask_high = test_df['true_altitude_m'] >= 8000
    mask_low = test_df['true_altitude_m'] < 8000
    
    for name, mask in [('Altitude < 8000m', mask_low), ('Altitude >= 8000m', mask_high)]:
        sub = test_df[mask]
        if len(sub) == 0:
            print(f"\n{name}: 0 samples")
            continue
            
        p_c = np.array(preds_cht)[mask]
        p_e = np.array(preds_egt)[mask]
        p_ot = np.array(preds_oilt)[mask]
        
        c_mae = mean_absolute_error(sub['measured_cht_cylinder_3_c'], p_c)
        e_mae = mean_absolute_error(sub['measured_egt_cylinder_3_c'], p_e)
        ot_mae = mean_absolute_error(sub['measured_oil_temperature_c'], p_ot)
        
        print(f"\n{name}")
        print(f"  Samples: {len(sub)}")
        print(f"  Ambient Temp Range: {sub['true_ambient_temperature_c'].min():.1f}C to {sub['true_ambient_temperature_c'].max():.1f}C")
        print(f"  RPM Range: {sub['true_rpm'].min():.1f} to {sub['true_rpm'].max():.1f}")
        print(f"  Throttle Range: {sub['true_throttle_pct'].min():.1f}% to {sub['true_throttle_pct'].max():.1f}%")
        print(f"  CHT MAE: {c_mae:.2f}")
        print(f"  EGT MAE: {e_mae:.2f}")
        print(f"  OilTemp MAE: {ot_mae:.2f}")

if __name__ == "__main__":
    main()
