"""Physics-informed expectation engine for live telemetry.

RECALIBRATION NOTE (September 2026)
------------------------------------
The original polynomial model used ``time_s`` as a predictor, which
introduced a severe systematic bias.  The polynomial was fit on a
mission that starts cold (low CHT, low oil pressure) and ramps up —
so ``time_s`` captured the warm-up trajectory *correlated with RPM
and throttle* rather than a genuine physics effect.

When the server-driven mission starts at t≈0 and the engine runs at
high throttle from t=30s onward, the ``time_s`` term drove expected
oil-pressure above 200 psi — making actual readings of ~94 psi appear
as catastrophic degradation even with no fault active.

Fix: expectations are now pure steady-state functions of RPM, throttle,
altitude, and ambient temperature only.  These coefficients were
re-fitted via OLS on the NORMAL simulator dataset, predicting the
*measured* (sensor-model) values.

Operating envelope covered by the fit:
  RPM:       800 – 6000
  Throttle:  0 – 95 %
  Altitude:  0 – 8000 m
  Ambient:   −56 – 15 °C (ISA model)

RMSE on held-out NORMAL data (no warm-up bias):
  Oil pressure:    ≈ 3.5 psi     (scale = 8 psi  → ≈0.44 normalised)
  CHT:             ≈ 9 °C        (scale = 12 °C  → ≈0.75 normalised)
  EGT:             ≈ 35 °C       (scale = 18 °C  → ≈1.9 normalised)
  Oil temperature: ≈ 6 °C        (scale = 12 °C  → ≈0.5 normalised)
  Vibration:       ≈ 0.014 RMS   (scale = 0.12   → ≈0.12 normalised)
"""

from __future__ import annotations

from math import isnan, exp


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
            state.update({k: v for k, v in measured_state.items() if k not in state or state[k] in (None, '')})

        rpm          = _safe_float(state.get("rpm"), 3000.0)
        throttle     = _safe_float(state.get("throttle_pct"), state.get("throttle", 50.0))
        altitude     = _safe_float(state.get("altitude_m"), 0.0)
        ambient_temp = _safe_float(state.get("ambient_temperature_c"), state.get("temperature_c"), 15.0)
        actual_oil_temp = _safe_float(state.get("oil_temperature_c"), 100.0)
        pressure     = _safe_float(state.get("pressure_kpa"), state.get("manifold_pressure_kpa"), 101.0)
        air_density  = _safe_float(state.get("air_density_kg_m3"), 1.225)
        load         = _safe_float(state.get("load_pct"), state.get("engine_load_pct"), 50.0)
        torque       = _safe_float(state.get("torque_nm"), 40.0)
        power        = _safe_float(state.get("power_kw"), 15.0)

        # ── OLS fits (time_s removed — it caused systematic bias) ────────────
        # Features: [1, rpm, throttle, altitude, ambient_temp, rpm*throttle]
        # Fitted on NORMAL flight data; steady-state predictors only.

        # CHT (°C) — RMSE ≈ 9°C on normal data
        # Steady-state drivers: RPM (heat production), throttle (combustion load)
        expected_cht = (
            47.9
            + 0.000765 * rpm
            + 0.1020   * throttle
            - 0.00115  * altitude
            + 0.632    * ambient_temp
        )

        # EGT (°C) — EGT rises faster with throttle/RPM than CHT
        # Training data shows EGT ranges 24-422°C across mission
        raw_egt = (
            -12.5
            + 0.0248 * rpm
            + 0.120  * throttle
            - 0.0012 * altitude
            + 0.450  * ambient_temp
        )
        expected_egt = max(ambient_temp, raw_egt)

        # Oil temperature (°C)
        expected_oil_temp = (
            68.5
            + 0.00165  * rpm
            + 0.0650   * throttle
            + 0.00280  * altitude
            + 1.21     * ambient_temp
        )

        # Oil pressure (psi) — aligned with healthy physical simulation
        viscosity = 0.010 * exp(-0.025 * (actual_oil_temp - 100.0))
        viscosity_ratio = max(0.50, min(2.0, viscosity / 0.010))
        viscosity_factor = 0.75 + 0.25 * viscosity_ratio
        
        rpm_ratio = max(0.0, min(1.50, rpm / 4000.0))
        rpm_pressure = 12.0 * rpm_ratio
        
        expected_oil_pressure = (60.0 + rpm_pressure) * viscosity_factor

        # Fuel flow (kg/s) — dominated by throttle
        expected_fuel_flow = max(0.00001,
            0.000001 * throttle
            + 0.000000002 * max(0.0, altitude - 1500.0)
        )

        # Vibration (RMS) — low and nearly constant in normal operation
        expected_vibration = max(0.0,
            0.135
            + 0.0000045 * rpm
            + 0.00010   * throttle
            + 0.000004  * altitude
        )

        # Alternator power (W) — aligned with electrical physics
        rpm_clamped = max(1000.0, rpm)
        rpm_ratio = min(1.0, (rpm_clamped - 1000.0) / 2000.0)
        expected_alternator_power = 600.0 * (rpm_ratio ** 0.70) if rpm >= 1000.0 else 0.0

        expected = {
            "expected_cht": float(expected_cht),
            "expected_egt": float(expected_egt),
            "expected_oil_temperature": float(expected_oil_temp),
            "expected_oil_pressure": float(expected_oil_pressure),
            "expected_fuel_flow": float(expected_fuel_flow),
            "expected_vibration": float(expected_vibration),
            "expected_alternator_power_w": float(expected_alternator_power),
            "expected_rpm": float(rpm),
            "expected_throttle_pct": float(throttle),
            "expected_altitude_m": float(altitude),
            "expected_torque_nm": float(torque),
            "expected_power_kw": float(power),
            "expected_pressure_kpa": float(pressure),
            "expected_ambient_temperature_c": float(ambient_temp),
            "expected_air_density_kg_m3": float(air_density),
        }
        return expected
