import sys; sys.path.insert(0, ".")
import pandas as pd, numpy as np
from numpy.linalg import lstsq
from intelligence.physics_expectation import PhysicsExpectationEngine

df = pd.read_csv("data/generated/_combined_training_dataset.csv")
normal = df[df["fault_type"] == "NORMAL"].copy()
rpm = normal["true_rpm"].values.astype(float)
throttle = normal["true_throttle_pct"].values.astype(float)
altitude = normal["true_altitude_m"].values.astype(float)
amb = normal["true_ambient_temperature_c"].values.astype(float)
X = np.column_stack([np.ones_like(rpm), rpm, throttle, altitude, amb])
y_oilp = normal["measured_oil_pressure_psi"].values.astype(float)
cht_cols = [c for c in normal.columns if "measured_cht_cylinder" in c]
y_cht = normal[cht_cols].mean(axis=1).values.astype(float)
c_oilp, _, _, _ = lstsq(X, y_oilp, rcond=None)
c_cht,  _, _, _ = lstsq(X, y_cht,  rcond=None)
print("OIL PRESSURE coefs:", [round(v, 8) for v in c_oilp])
print("CHT coefs:", [round(v, 8) for v in c_cht])
print()

engine = PhysicsExpectationEngine()
pts = [
    (800,  0,  3500,  5, 78, 45, "IDLE     t=5s"),
    (800,  0,  3500,  5, 78, 39, "IDLE     t=20s"),
    (5300, 88, 3500,  5, 94, 48, "CLIMB    t=50s"),
    (6000, 90, 3500,  2, 70, 80, "CRUISE   t=90s"),
]
print("Current model predictions:")
for rpm_v, thr_v, alt_v, amb_v, a_p, a_c, lbl in pts:
    op = {"rpm": rpm_v, "throttle_pct": thr_v, "altitude_m": alt_v, "ambient_temperature_c": amb_v}
    exp = engine.calculate(operating_state=op)
    print(f"  {lbl:20s}  ExpOP={exp['expected_oil_pressure']:.1f}  ActOP={a_p}  Dev={a_p-exp['expected_oil_pressure']:+.1f}  |  ExpCHT={exp['expected_cht']:.1f}  ActCHT={a_c}")

print()
print("OLS model predictions (reference):")
for rpm_v, thr_v, alt_v, amb_v, a_p, a_c, lbl in pts:
    row = np.array([1.0, rpm_v, thr_v, alt_v, amb_v])
    pred_p = max(10.0, float(row @ c_oilp))
    pred_c = float(row @ c_cht)
    print(f"  {lbl:20s}  ExpOP={pred_p:.1f}  ActOP={a_p}  Dev={a_p-pred_p:+.1f}  |  ExpCHT={pred_c:.1f}  ActCHT={a_c}")
