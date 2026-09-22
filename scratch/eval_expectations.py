import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import sys
sys.path.insert(0, '.')
from intelligence.physics_expectation import PhysicsExpectationEngine

import warnings
warnings.filterwarnings('ignore')

df = pd.read_csv('data/generated/aeris_twin_normal.csv')

df['meas_cht'] = df[['measured_cht_cylinder_1_c', 'measured_cht_cylinder_2_c', 'measured_cht_cylinder_3_c', 'measured_cht_cylinder_4_c']].max(axis=1)
df['meas_egt'] = df[['measured_egt_cylinder_1_c', 'measured_egt_cylinder_2_c', 'measured_egt_cylinder_3_c', 'measured_egt_cylinder_4_c']].max(axis=1)
df['meas_oil_temp'] = df['measured_oil_temperature_c']
df['meas_oil_pressure'] = df['measured_oil_pressure_psi']

print('EGT < 0 at startup?', df.loc[df['simulation_time_s'] < 10, 'meas_egt'].min())

engine = PhysicsExpectationEngine()
ols_cht, ols_egt, ols_oil_t, ols_oil_p = [], [], [], []

for _, row in df.iterrows():
    exp = engine.calculate(operating_state={
        'rpm': row['true_rpm'],
        'throttle_pct': row['true_throttle_pct'],
        'altitude_m': row['true_altitude_m'],
        'ambient_temperature_c': row['true_ambient_temperature_c'],
        'oil_temperature_c': row['measured_oil_temperature_c']
    })
    ols_cht.append(exp['expected_cht'])
    ols_egt.append(exp['expected_egt'])
    ols_oil_t.append(exp['expected_oil_temperature'])
    ols_oil_p.append(exp['expected_oil_pressure'])

df['ols_cht'] = ols_cht
df['ols_egt'] = ols_egt
df['ols_oil_temp'] = ols_oil_t
df['ols_oil_pressure'] = ols_oil_p

split_idx = int(len(df) * 0.8)
train = df.iloc[:split_idx]
test = df.iloc[split_idx:]

features = ['true_rpm', 'true_throttle_pct', 'true_altitude_m', 'true_ambient_temperature_c']
targets = ['meas_cht', 'meas_egt', 'meas_oil_temp', 'meas_oil_pressure']

rf = RandomForestRegressor(n_estimators=20, random_state=42, max_depth=10)
rf.fit(train[features], train[targets])

preds = rf.predict(df[features])
df['rf_cht'] = preds[:, 0]
df['rf_egt'] = preds[:, 1]
df['rf_oil_temp'] = preds[:, 2]
df['rf_oil_pressure'] = preds[:, 3]

alpha = 0.05
for target in ['cht', 'egt', 'oil_temp', 'oil_pressure']:
    df[f'rf_ema_{target}'] = df[f'rf_{target}'].ewm(alpha=alpha, adjust=False).mean()

def report_mae(subset, name):
    if len(subset) == 0:
        return
    print(f'\n--- {name} ({len(subset)} samples) ---')
    print(f"OLS MAE    - CHT: {np.abs(subset['meas_cht'] - subset['ols_cht']).mean():.2f} | EGT: {np.abs(subset['meas_egt'] - subset['ols_egt']).mean():.2f} | OilT: {np.abs(subset['meas_oil_temp'] - subset['ols_oil_temp']).mean():.2f} | OilP: {np.abs(subset['meas_oil_pressure'] - subset['ols_oil_pressure']).mean():.2f}")
    print(f"RF MAE     - CHT: {np.abs(subset['meas_cht'] - subset['rf_cht']).mean():.2f} | EGT: {np.abs(subset['meas_egt'] - subset['rf_egt']).mean():.2f} | OilT: {np.abs(subset['meas_oil_temp'] - subset['rf_oil_temp']).mean():.2f} | OilP: {np.abs(subset['meas_oil_pressure'] - subset['rf_oil_pressure']).mean():.2f}")
    print(f"RF+EMA MAE - CHT: {np.abs(subset['meas_cht'] - subset['rf_ema_cht']).mean():.2f} | EGT: {np.abs(subset['meas_egt'] - subset['rf_ema_egt']).mean():.2f} | OilT: {np.abs(subset['meas_oil_temp'] - subset['rf_ema_oil_temp']).mean():.2f} | OilP: {np.abs(subset['meas_oil_pressure'] - subset['rf_ema_oil_pressure']).mean():.2f}")

report_mae(df, 'OVERALL')
for phase in df['mission_phase'].unique():
    report_mae(df[df['mission_phase'] == phase], f'PHASE: {phase}')

report_mae(df[df['simulation_time_s'] <= 30], 'STARTUP (first 30s)')
report_mae(df[df['true_ambient_temperature_c'] > 30], 'HOT WEATHER (>30C)')
report_mae(df[df['true_altitude_m'] > 2000], 'HIGH ALTITUDE (>2000m)')
