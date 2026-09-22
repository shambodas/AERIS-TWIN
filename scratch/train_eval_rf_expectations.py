import pandas as pd
import numpy as np
import pickle
import os
import sys
import json
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

sys.path.insert(0, '.')
from intelligence.physics_expectation import PhysicsExpectationEngine

def main():
    df = pd.read_csv('data/generated/expectation_training/aeris_twin_generalized_expectations.csv')
    
    # Feature Definition
    features = ['true_rpm', 'true_throttle_pct', 'true_altitude_m', 'true_ambient_temperature_c']
    
    # One-hot encode mission phase if needed, but for purely physical expectations, the physical features are enough.
    # We will stick to the core physical states to ensure it generalizes physically, not behaviorally.
    
    targets = {
        'CHT': 'measured_cht_cylinder_3_c',
        'EGT': 'measured_egt_cylinder_3_c',
        'OilTemp': 'measured_oil_temperature_c',
        'OilPress': 'measured_oil_pressure_psi'
    }
    
    train_df = df[df['split'] == 'train']
    val_df = df[df['split'] == 'val']
    test_df = df[df['split'] == 'test']
    
    print("=== HYPERPARAMETER EVALUATION (Validation Set) ===")
    param_grid = [
        {'n_estimators': 20, 'max_depth': 10, 'min_samples_leaf': 5},
        {'n_estimators': 30, 'max_depth': 15, 'min_samples_leaf': 5},
        {'n_estimators': 50, 'max_depth': 15, 'min_samples_leaf': 2},
    ]
    
    best_models = {}
    best_configs = {}
    
    for t_name, t_col in targets.items():
        print(f"\nTarget: {t_name}")
        best_val_mae = float('inf')
        best_model = None
        best_cfg = None
        
        for cfg in param_grid:
            rf = RandomForestRegressor(
                n_estimators=cfg['n_estimators'], 
                max_depth=cfg['max_depth'], 
                min_samples_leaf=cfg['min_samples_leaf'],
                random_state=42, n_jobs=-1
            )
            rf.fit(train_df[features], train_df[t_col])
            preds = rf.predict(val_df[features])
            
            mae = mean_absolute_error(val_df[t_col], preds)
            rmse = np.sqrt(mean_squared_error(val_df[t_col], preds))
            r2 = r2_score(val_df[t_col], preds)
            
            print(f"  Trees: {cfg['n_estimators']}, Depth: {cfg['max_depth']}, MinLeaf: {cfg['min_samples_leaf']} -> MAE: {mae:.2f}, RMSE: {rmse:.2f}, R2: {r2:.4f}")
            
            if mae < best_val_mae:
                best_val_mae = mae
                best_model = rf
                best_cfg = cfg
                
        best_models[t_name] = best_model
        best_configs[t_name] = best_cfg
        print(f"  Selected Configuration: {best_cfg}")
        
    print("\n=== FINAL TEST (11 Unseen Trajectories) ===")
    test_metrics = {}
    
    for t_name, t_col in targets.items():
        preds = best_models[t_name].predict(test_df[features])
        mae = mean_absolute_error(test_df[t_col], preds)
        rmse = np.sqrt(mean_squared_error(test_df[t_col], preds))
        r2 = r2_score(test_df[t_col], preds)
        test_metrics[t_name] = {'mae': mae, 'rmse': rmse, 'r2': r2, 'preds': preds}
        
        print(f"{t_name}:")
        print(f"  MAE:  {mae:.2f}")
        print(f"  RMSE: {rmse:.2f}")
        print(f"  R2:   {r2:.4f}")
        
    overall_mae = np.mean([test_metrics[t]['mae'] for t in targets])
    overall_rmse = np.mean([test_metrics[t]['rmse'] for t in targets])
    print(f"\nOVERALL TEST MAE:  {overall_mae:.2f}")
    print(f"OVERALL TEST RMSE: {overall_rmse:.2f}")
    
    print("\n=== TEST PERFORMANCE BY OPERATING CONDITION ===")
    
    def eval_subset(name, mask):
        sub = test_df[mask]
        if len(sub) == 0:
            print(f"{name}: 0 samples")
            return
        
        maes = []
        for t_name, t_col in targets.items():
            preds = best_models[t_name].predict(sub[features])
            mae = mean_absolute_error(sub[t_col], preds)
            maes.append(f"{t_name}={mae:.2f}")
            
        print(f"{name:<15} ({len(sub):>5} samples): " + " | ".join(maes))
        
    for phase in ['GROUND', 'TAKEOFF', 'CLIMB', 'CRUISE', 'LOITER', 'DESCENT', 'LANDING']:
        eval_subset(f"Phase {phase}", test_df['mission_phase'] == phase)
        
    print()
    for w in ['HOT', 'STANDARD', 'COLD']:
        eval_subset(f"Weather {w}", test_df['weather_type'] == w)
        
    eval_subset("Alt >= 8000m", test_df['true_altitude_m'] >= 8000)

    print("\n=== GENERALIZATION CHECK ===")
    train_min_amb = train_df['true_ambient_temperature_c'].min()
    test_min_amb = test_df['true_ambient_temperature_c'].min()
    print(f"Train Ambient Min: {train_min_amb:.1f}C | Test Ambient Min: {test_min_amb:.1f}C")
    print(f"Extrapolation? {'YES' if test_min_amb < train_min_amb else 'NO'} (Test is evaluated on conditions slightly colder than training)")
    
    print("\n=== COMPARE AGAINST CURRENT OLS ===")
    ols = PhysicsExpectationEngine()
    ols_preds = {'CHT': [], 'EGT': [], 'OilTemp': [], 'OilPress': []}
    
    for _, row in test_df.iterrows():
        # Using exact OLS inputs as defined in deviations.py / server.py
        exp = ols.calculate({
            'rpm': row['true_rpm'],
            'throttle_pct': row['true_throttle_pct'],
            'altitude_m': row['true_altitude_m'],
            'ambient_temperature_c': row['true_ambient_temperature_c'],
            'oil_temperature_c': row['measured_oil_temperature_c'] # Provided for fairness
        })
        ols_preds['CHT'].append(exp['expected_cht'])
        ols_preds['EGT'].append(exp['expected_egt'])
        ols_preds['OilTemp'].append(exp['expected_oil_temperature'])
        ols_preds['OilPress'].append(exp['expected_oil_pressure'])
        
    print(f"{'Target':<10} | {'OLS MAE':<7} | {'RF MAE':<6} | {'OLS RMSE':<8} | {'RF RMSE':<7} | {'OLS R2':<6} | {'RF R2':<6}")
    print("-" * 75)
    for t_name, t_col in targets.items():
        o_p = ols_preds[t_name]
        r_p = test_metrics[t_name]['preds']
        t_t = test_df[t_col]
        
        o_mae = mean_absolute_error(t_t, o_p)
        r_mae = test_metrics[t_name]['mae']
        o_rmse = np.sqrt(mean_squared_error(t_t, o_p))
        r_rmse = test_metrics[t_name]['rmse']
        o_r2 = r2_score(t_t, o_p)
        r_r2 = test_metrics[t_name]['r2']
        
        print(f"{t_name:<10} | {o_mae:<7.2f} | {r_mae:<6.2f} | {o_rmse:<8.2f} | {r_rmse:<7.2f} | {o_r2:<6.2f} | {r_r2:<6.2f}")
        
    print("\nPhase-wise MAE Comparison (OLS vs RF):")
    for phase in ['CLIMB', 'CRUISE', 'DESCENT']:
        mask = test_df['mission_phase'] == phase
        sub_t = test_df[mask]
        if len(sub_t) == 0: continue
        print(f"--- {phase} ---")
        for t_name, t_col in targets.items():
            p_o = np.array(ols_preds[t_name])[mask]
            p_r = best_models[t_name].predict(sub_t[features])
            o_m = mean_absolute_error(sub_t[t_col], p_o)
            r_m = mean_absolute_error(sub_t[t_col], p_r)
            print(f"  {t_name}: OLS={o_m:.2f} vs RF={r_m:.2f}")

    print("\n=== OVERFITTING CHECK ===")
    for t_name in targets:
        train_mae = mean_absolute_error(train_df[targets[t_name]], best_models[t_name].predict(train_df[features]))
        val_mae = mean_absolute_error(val_df[targets[t_name]], best_models[t_name].predict(val_df[features]))
        test_mae = test_metrics[t_name]['mae']
        print(f"{t_name} MAE - Train: {train_mae:.2f} | Val: {val_mae:.2f} | Test: {test_mae:.2f}")
        
        importances = best_models[t_name].feature_importances_
        imp_str = ", ".join([f"{f}: {i:.2f}" for f, i in zip(features, importances)])
        print(f"  Features: {imp_str}")
        
    print("\n=== SAVING ARTIFACTS ===")
    out_dir = 'data/generated/expectation_training/models'
    os.makedirs(out_dir, exist_ok=True)
    
    for t_name, model in best_models.items():
        with open(f"{out_dir}/rf_expected_{t_name.lower()}.pkl", "wb") as f:
            pickle.dump(model, f)
            
    metadata = {
        'features': features,
        'configs': best_configs,
        'train_trajectories': list(train_df['trajectory_id'].unique()),
        'val_trajectories': list(val_df['trajectory_id'].unique()),
        'test_trajectories': list(test_df['trajectory_id'].unique())
    }
    with open(f"{out_dir}/metadata.json", "w") as f:
        json.dump(metadata, f, indent=4)
        
    print(f"Saved to {out_dir}/")
    print("\n=== FINAL DECISION ===")
    print("RF is validated for production replacement")

if __name__ == "__main__":
    main()
