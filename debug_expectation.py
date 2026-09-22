import sys; sys.path.insert(0, '.')
from intelligence.physics_expectation import PhysicsExpectationEngine
import pandas as pd

engine = PhysicsExpectationEngine()

print("=== IDLE STATE (RPM=800, throttle=0, t=5.9s, alt=3500) ===")
op = {'rpm': 800, 'throttle_pct': 0.0, 'altitude_m': 3500, 'time_s': 5.9, 'ambient_temperature_c': 5.0}
exp = engine.calculate(operating_state=op)
actual_oil = 78.0
actual_cht = 45.0
dev_oil = actual_oil - exp["expected_oil_pressure"]
dev_cht = actual_cht - exp["expected_cht"]
print(f"  Expected oil_pressure: {exp['expected_oil_pressure']:.1f} psi  actual: {actual_oil}  dev: {dev_oil:+.1f}")
print(f"  Expected CHT:          {exp['expected_cht']:.1f} C   actual: {actual_cht}  dev: {dev_cht:+.1f}")
print(f"  -> oil_pressure_deviation (normalized by 8.0): {dev_oil/8.0:+.2f}")
print(f"  -> cht_deviation (normalized by 12.0): {dev_cht/12.0:+.2f}")
print()

print("=== CLIMB STATE (RPM=5300, throttle=88, t=50s, alt=3500) ===")
op2 = {'rpm': 5300, 'throttle_pct': 88.0, 'altitude_m': 3500, 'time_s': 50.0, 'ambient_temperature_c': 5.0}
exp2 = engine.calculate(operating_state=op2)
actual_oil2 = 94.0
actual_cht2 = 48.0
dev_oil2 = actual_oil2 - exp2["expected_oil_pressure"]
dev_cht2 = actual_cht2 - exp2["expected_cht"]
print(f"  Expected oil_pressure: {exp2['expected_oil_pressure']:.1f} psi  actual: {actual_oil2}  dev: {dev_oil2:+.1f}")
print(f"  Expected CHT:          {exp2['expected_cht']:.1f} C   actual: {actual_cht2}  dev: {dev_cht2:+.1f}")
print(f"  -> oil_pressure_deviation (normalized by 8.0): {dev_oil2/8.0:+.2f}")
print(f"  -> cht_deviation (normalized by 12.0): {dev_cht2/12.0:+.2f}")
print()

# Core issue: what does training data look like at t=50s, throttle=88%?
df = pd.read_csv('data/generated/_combined_training_dataset.csv')
normal = df[df['fault_type'] == 'NORMAL'].copy()
mask = (normal['true_throttle_pct'] > 85) & (normal['simulation_time_s'].between(45, 55))
sample = normal[mask]
print(f"Training samples near t=50, thr>85%: {len(sample)}")
if len(sample):
    cols = ['simulation_time_s','true_rpm','true_throttle_pct','measured_cht_cylinder_1_c','measured_oil_pressure_psi']
    print(sample[cols].head(5).to_string())
    print()
    print(f"  Training CHT at t=50,thr>85%: {sample['measured_cht_cylinder_1_c'].mean():.1f} C mean")
    print(f"  Training OilP at t=50,thr>85%: {sample['measured_oil_pressure_psi'].mean():.1f} psi mean")
print()

# What is the actual engine CHT in training data for the FULL mission?
print("=== TRAINING DATA: CHT vs simulation time for NORMAL ===")
time_bins = [(0,30), (30,60), (60,90), (90,120)]
for lo, hi in time_bins:
    seg = normal[normal['simulation_time_s'].between(lo, hi)]
    if len(seg):
        print(f"  t={lo}-{hi}s: CHT mean={seg['measured_cht_cylinder_1_c'].mean():.1f} C, OilP mean={seg['measured_oil_pressure_psi'].mean():.1f} psi, RPM mean={seg['true_rpm'].mean():.0f}, Thr mean={seg['true_throttle_pct'].mean():.1f}%")
