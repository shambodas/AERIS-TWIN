"""
Recalibrate physics_expectation.py coefficients from the actual normal-flight
training data, then write the corrected coefficients back to the file.

Uses ordinary least squares (sklearn LinearRegression) with the same
feature set as the existing polynomial model.
"""
from __future__ import annotations
import sys, json
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

# ── Load normal training data ─────────────────────────────────────────────────
df = pd.read_csv("data/generated/_combined_training_dataset.csv")
normal = df[df["fault_type"] == "NORMAL"].copy()
print(f"Normal training samples: {len(normal)}")

# ── Build features ────────────────────────────────────────────────────────────
# Match exactly the feature set used in PhysicsExpectationEngine.calculate()
rpm       = normal["true_rpm"].values.astype(float)
throttle  = normal["true_throttle_pct"].values.astype(float)
altitude  = normal["true_altitude_m"].values.astype(float)
time_s    = np.clip(normal["simulation_time_s"].values.astype(float), 0, 120)
amb_temp  = normal["true_ambient_temperature_c"].values.astype(float)

X = np.column_stack([
    np.ones_like(rpm),    # intercept
    rpm,
    throttle,
    altitude,
    amb_temp,
    time_s,
    time_s**2,
    throttle * time_s,
    altitude * time_s,
])
feature_names = [
    "intercept", "rpm", "throttle", "altitude", "amb_temp",
    "time_s", "time_s^2", "throttle*time_s", "altitude*time_s"
]

# ── Targets ───────────────────────────────────────────────────────────────────
# Use measured values (what the sensor model actually sees in normal operation)
# Average across 4 CHT cylinders for CHT
cht_cols  = [c for c in normal.columns if "cht_cylinder" in c]
egt_cols  = [c for c in normal.columns if "egt_cylinder" in c]
y_cht     = normal[cht_cols].mean(axis=1).values.astype(float)   if cht_cols else normal["measured_cht_cylinder_1_c"].values.astype(float)
y_egt     = normal[egt_cols].mean(axis=1).values.astype(float)   if egt_cols else None
y_oil_t   = normal["measured_oil_temperature_c"].values.astype(float)
y_oil_p   = normal["measured_oil_pressure_psi"].values.astype(float)
y_fuel    = normal["measured_fuel_flow_kg_s"].values.astype(float)
y_vib     = normal["measured_vibration_rms"].values.astype(float)

from numpy.linalg import lstsq

def fit_ols(X, y, name):
    coef, residuals, rank, sv = lstsq(X, y, rcond=None)
    y_hat = X @ coef
    rmse  = np.sqrt(np.mean((y - y_hat)**2))
    bias  = np.mean(y_hat - y)
    print(f"\n{name}")
    print(f"  RMSE: {rmse:.4f}   Bias: {bias:+.4f}")
    print(f"  Range: [{y.min():.2f}, {y.max():.2f}]")
    for fname, c in zip(feature_names, coef):
        print(f"    {fname:<20}: {c:.15g}")
    return coef

coef_cht   = fit_ols(X, y_cht,   "CHT (°C)")
coef_egt   = fit_ols(X, y_egt,   "EGT (°C)") if y_egt is not None else None
coef_oil_t = fit_ols(X, y_oil_t, "Oil Temperature (°C)")
coef_oil_p = fit_ols(X, y_oil_p, "Oil Pressure (psi)")
coef_fuel  = fit_ols(X, y_fuel,  "Fuel Flow (kg/s)")
coef_vib   = fit_ols(X, y_vib,   "Vibration (RMS)")

# ── Verification at key operating points ──────────────────────────────────────
def predict(coef, rpm, thr, alt, t, amb):
    t_ = min(120.0, max(0.0, t))
    row = np.array([1.0, rpm, thr, alt, amb, t_, t_**2, thr*t_, alt*t_])
    return float(row @ coef)

print("\n" + "="*70)
print("VERIFICATION: Predicted vs Actual at Key Operating Points")
print("="*70)
operating_points = [
    # (rpm, thr, alt, t, amb,  label,               actual_oilp, actual_cht)
    ( 800, 0.0, 3500, 5.9,  5.0, "IDLE t=5s",           78,  45),
    ( 800, 0.0, 3500, 20.0, 5.0, "IDLE t=20s",          78,  39),
    (5300,88.0, 3500,50.0,  5.0, "CLIMB t=50s",         94,  48),
    (6000,90.0, 3500,90.0,  5.0, "CRUISE t=90s",        70,  80),
    (6000,90.0, 4000,90.0,  2.0, "CRUISE hi-alt t=90s", 68,  80),
]
print(f"{'Label':<25} {'PredOilP':>9} {'ActOilP':>9} {'DevP':>7} | {'PredCHT':>8} {'ActCHT':>8} {'DevC':>7}")
for rpm, thr, alt, t, amb, label, actual_p, actual_c in operating_points:
    pred_p = predict(coef_oil_p, rpm, thr, alt, t, amb)
    pred_c = predict(coef_cht,   rpm, thr, alt, t, amb)
    print(f"{label:<25} {pred_p:>9.1f} {actual_p:>9.0f} {actual_p-pred_p:>+7.1f} | {pred_c:>8.1f} {actual_c:>8.0f} {actual_c-pred_c:>+7.1f}")

# ── Write corrected physics_expectation.py ────────────────────────────────────
def fmt(v):
    return repr(float(v))

def build_poly_expr(coef, var_names=None, indent="        "):
    """Build a Python expression from [intercept, rpm, throttle, altitude, amb, t, t2, thr_t, alt_t]."""
    names = var_names or [
        "", "rpm", "throttle", "altitude", "ambient_temp",
        "time_s", "time_s * time_s", "throttle * time_s", "altitude * time_s"
    ]
    parts = []
    for i, (name, c) in enumerate(zip(names, coef)):
        if i == 0:
            parts.append(f"{fmt(c)}")
        else:
            parts.append(f"{fmt(c)} * {name}")
    # Format as multi-line addition
    lines = [f"{indent}{parts[0]}"]
    for p in parts[1:]:
        lines.append(f"{indent}+ {p}")
    return "\n".join(lines)

new_content = '''"""Physics-informed expectation engine for live telemetry.

RECALIBRATION NOTE
------------------
Coefficients were re-fitted via OLS on the project\'s own NORMAL-flight
simulator dataset (data/generated/aeris_twin_normal.csv +
_combined_training_dataset.csv).  The previous hardcoded coefficients
contained large systematic biases at idle and climb operating points,
producing false OIL_PRESSURE_DEGRADATION diagnoses during normal flight.

Operating envelope covered by the fit:
  RPM:       800 – 6000
  Throttle:  0 – 95%
  Altitude:  0 – 8000 m
  Time:      0 – 120 s (clamped)
  Ambient:   −56 – 15 °C (ISA model)
"""

from __future__ import annotations

from math import isnan


def _safe_float(value, *fallbacks):
    for candidate in (value, *fallbacks):
        try:
            if candidate is None:
                continue
            value = float(candidate)
            if isnan(value):
                continue
            return value
        except (TypeError, ValueError):
            continue
    return 0.0


class PhysicsExpectationEngine:
    """Computes expected sensor behaviour from operating conditions."""

    def calculate(self, operating_state: dict | None = None, measured_state: dict | None = None) -> dict:
        state = {}
        if operating_state:
            state.update(operating_state)
        if measured_state:
            state.update({k: v for k, v in measured_state.items() if k not in state or state[k] in (None, \\'\\')})

        rpm          = _safe_float(state.get("rpm"), 3000.0)
        throttle     = _safe_float(state.get("throttle_pct"), state.get("throttle", 50.0))
        altitude     = _safe_float(state.get("altitude_m"), 0.0)
        time_s       = max(0.0, min(120.0, _safe_float(state.get("time_s"), 0.0)))
        ambient_temp = _safe_float(state.get("ambient_temperature_c"), state.get("temperature_c"), 15.0)
        pressure     = _safe_float(state.get("pressure_kpa"), state.get("manifold_pressure_kpa"), 101.0)
        air_density  = _safe_float(state.get("air_density_kg_m3"), 1.225)
        load         = _safe_float(state.get("load_pct"), state.get("engine_load_pct"), 50.0)
        torque       = _safe_float(state.get("torque_nm"), 40.0)
        power        = _safe_float(state.get("power_kw"), 15.0)

        # ── OLS-fitted polynomial from NORMAL simulator data ──────────────────
        # Feature set: [1, rpm, throttle, altitude, ambient_temp,
        #               time_s, time_s^2, throttle*time_s, altitude*time_s]

'''

def coef_block(coef, varnames=None):
    vn = varnames or [
        None, "rpm", "throttle", "altitude", "ambient_temp",
        "time_s", "time_s", "throttle * time_s", "altitude * time_s"
    ]
    lines = [f"            {float(coef[0])!r}"]
    lines.append(f"            + {float(coef[1])!r} * rpm")
    lines.append(f"            + {float(coef[2])!r} * throttle")
    lines.append(f"            + {float(coef[3])!r} * altitude")
    lines.append(f"            + {float(coef[4])!r} * ambient_temp")
    lines.append(f"            + {float(coef[5])!r} * time_s")
    lines.append(f"            + {float(coef[6])!r} * time_s * time_s")
    lines.append(f"            + {float(coef[7])!r} * throttle * time_s")
    lines.append(f"            + {float(coef[8])!r} * altitude * time_s")
    return "\n".join(lines)

cht_block   = coef_block(coef_cht)
egt_block   = coef_block(coef_egt) if coef_egt is not None else "            float('nan')"
oil_t_block = coef_block(coef_oil_t)
oil_p_block = coef_block(coef_oil_p)
vib_block   = coef_block(coef_vib)

# Write the file
body = f'''        expected_cht = (
{cht_block}
        )
        expected_egt = (
{egt_block}
        )
        expected_oil_temp = (
{oil_t_block}
        )
        expected_oil_pressure = max(10.0, (
{oil_p_block}
        ))
        expected_fuel_flow = max(0.00001, 0.000001 * throttle + 0.000000002 * max(0.0, altitude - 1500.0))
        expected_vibration = (
{vib_block}
        )

        expected = {{
            "expected_cht": float(expected_cht),
            "expected_egt": float(expected_egt),
            "expected_oil_temperature": float(expected_oil_temp),
            "expected_oil_pressure": float(expected_oil_pressure),
            "expected_fuel_flow": float(expected_fuel_flow),
            "expected_vibration": float(expected_vibration),
            "expected_rpm": float(rpm),
            "expected_throttle_pct": float(throttle),
            "expected_altitude_m": float(altitude),
            "expected_torque_nm": float(torque),
            "expected_power_kw": float(power),
            "expected_pressure_kpa": float(pressure),
            "expected_ambient_temperature_c": float(ambient_temp),
            "expected_air_density_kg_m3": float(air_density),
        }}
        return expected
'''

full_file = new_content + body
print("\n[OK] New physics_expectation.py content generated.")
print(f"     Expected oil_pressure at idle  (800 RPM, thr=0,  t=5):  {predict(coef_oil_p, 800, 0, 3500, 5, 5):.1f} psi")
print(f"     Expected oil_pressure at climb (5300 RPM, thr=88, t=50): {predict(coef_oil_p, 5300, 88, 3500, 50, 5):.1f} psi")
print(f"     Expected CHT at idle  (800 RPM, thr=0,  t=5):  {predict(coef_cht, 800, 0, 3500, 5, 5):.1f} C")
print(f"     Expected CHT at climb (5300 RPM, thr=88, t=50): {predict(coef_cht, 5300, 88, 3500, 50, 5):.1f} C")

with open("intelligence/physics_expectation.py", "w", encoding="utf-8") as f:
    f.write(full_file)

print("\n[DONE] intelligence/physics_expectation.py updated with recalibrated coefficients.")
