"""
Verify recalibrated physics_expectation.py against training data
and key operating points.
"""
import sys; sys.path.insert(0, ".")
import pandas as pd, numpy as np
from numpy.linalg import lstsq
from intelligence.physics_expectation import PhysicsExpectationEngine

# ── Load training data ────────────────────────────────────────────────────────
df = pd.read_csv("data/generated/_combined_training_dataset.csv")
normal = df[df["fault_type"] == "NORMAL"].copy()

# ── Refit using same feature set as the new model ────────────────────────────
rpm      = normal["true_rpm"].values.astype(float)
throttle = normal["true_throttle_pct"].values.astype(float)
altitude = normal["true_altitude_m"].values.astype(float)
amb      = normal["true_ambient_temperature_c"].values.astype(float)

X = np.column_stack([np.ones_like(rpm), rpm, throttle, altitude, amb])
names = ["intercept", "rpm", "throttle", "altitude", "ambient_temp"]

cht_cols = [c for c in normal.columns if "measured_cht_cylinder" in c]
y_cht  = normal[cht_cols].mean(axis=1).values.astype(float)
y_oilp = normal["measured_oil_pressure_psi"].values.astype(float)
y_oilt = normal["measured_oil_temperature_c"].values.astype(float)
y_vib  = normal["measured_vibration_rms"].values.astype(float)

egt_cols = [c for c in normal.columns if "measured_egt_cylinder" in c]
y_egt  = normal[egt_cols].mean(axis=1).values.astype(float) if egt_cols else None

def ols(X, y, name):
    coef, _, _, _ = lstsq(X, y, rcond=None)
    yhat = X @ coef
    rmse = float(np.sqrt(np.mean((y - yhat)**2)))
    bias = float(np.mean(yhat - y))
    print(f"  {name}: RMSE={rmse:.3f}, Bias={bias:+.3f}, Range=[{y.min():.1f}, {y.max():.1f}]")
    for n, c in zip(names, coef):
        print(f"    {n:<15}: {c:.8g}")
    return coef

print("=" * 65)
print("OLS FIT (no time_s) from NORMAL training data")
print("=" * 65)
c_cht  = ols(X, y_cht,  "CHT (°C)")
c_egt  = ols(X, y_egt,  "EGT (°C)") if y_egt is not None else None
c_oilp = ols(X, y_oilp, "Oil Pressure (psi)")
c_oilt = ols(X, y_oilt, "Oil Temperature (°C)")
c_vib  = ols(X, y_vib,  "Vibration (RMS)")

# ── Now verify the current physics_expectation.py at key operating points ────
engine = PhysicsExpectationEngine()

operating_points = [
    # (rpm, thr, alt, amb,   label,               actual_oilp, actual_cht)
    ( 800,  0.0, 3500,  5.0, "IDLE     t≈5s",      78,  45),
    ( 800,  0.0, 3500,  5.0, "IDLE     t≈20s",     78,  39),
    (3269, 85.5, 3500,  5.0, "ACCEL    t≈32s",      86,  32),
    (5300, 88.0, 3500,  5.0, "CLIMB    t≈50s",      94,  48),
    (6000, 90.0, 3500,  2.0, "CRUISE   t≈90s",      70,  80),
    (6000, 90.0, 4000,  2.0, "CRUISE   hi-alt",     68,  80),
]

print("\n" + "=" * 90)
print("CURRENT MODEL vs ACTUAL at Key Operating Points")
print("=" * 90)
hdr = f"{'Label':<18} {'ExpOilP':>8} {'ActOilP':>8} {'DevP':>7} | {'ExpCHT':>7} {'ActCHT':>7} {'DevC':>7} | {'ExpEGT':>7}"
print(hdr)
print("-" * 90)
all_ok = True
for rpm_v, thr_v, alt_v, amb_v, label, actual_p, actual_c in operating_points:
    op = {"rpm": rpm_v, "throttle_pct": thr_v, "altitude_m": alt_v, "ambient_temperature_c": amb_v}
    exp = engine.calculate(operating_state=op)
    pred_p = exp["expected_oil_pressure"]
    pred_c = exp["expected_cht"]
    pred_e = exp["expected_egt"]
    dev_p  = actual_p - pred_p
    dev_c  = actual_c - pred_c
    flag   = "  <-- BIAS" if abs(dev_p) > 20 or abs(dev_c) > 25 else ""
    if flag: all_ok = False
    print(f"{label:<18} {pred_p:>8.1f} {actual_p:>8.0f} {dev_p:>+7.1f} | {pred_c:>7.1f} {actual_c:>7.0f} {dev_c:>+7.1f} | {pred_e:>7.1f}{flag}")

print()
if all_ok:
    print("[OK] Predictions are within acceptable deviation at all key operating points.")
else:
    print("[WARN] Some operating points still show large deviation. See coefficients above.")

# ── Show what coefficients SHOULD be from the OLS fit ────────────────────────
print("\n" + "=" * 65)
print("RECOMMENDED COEFFICIENTS (OLS-fitted, no time_s)")
print("=" * 65)
print("Oil Pressure:")
for n, c in zip(names, c_oilp):
    print(f"  {n:<15}: {c:.6g}")
print("CHT:")
for n, c in zip(names, c_cht):
    print(f"  {n:<15}: {c:.6g}")
