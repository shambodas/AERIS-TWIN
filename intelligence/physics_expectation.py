"""Physics-informed expectation engine for live telemetry.

RECALIBRATION NOTE (September 2026)
------------------------------------
Integrated hybrid RF + OLS expectation model.
- Random Forest models predict thermal targets (CHT, EGT, Oil Temperature).
- OLS equation remains for Oil Pressure.
"""

from __future__ import annotations
from math import isnan, exp
import pickle
import numpy as np
import os
import warnings
import time

# Suppress sklearn feature names warning
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

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

    def __init__(self):
        # Load RF models
        base_dir = os.path.dirname(__file__)
        model_dir = os.path.join(base_dir, '..', 'data', 'generated', 'expectation_training', 'models')
        
        self.rf_models = {}
        for target in ['cht', 'egt', 'oiltemp']:
            model_path = os.path.join(model_dir, f'rf_expected_{target}.pkl')
            if os.path.exists(model_path):
                with open(model_path, 'rb') as f:
                    self.rf_models[target] = pickle.load(f)
            else:
                self.rf_models[target] = None
                print(f"WARNING: Model not found at {model_path}")

        # Caching layer to mitigate RF inference bottleneck in real-time loop
        self.last_update_time = -999.0
        self.last_inputs = None
        self.cached_expected = None

    def invalidate_cache(self):
        """Force the RF models to re-evaluate on the next call."""
        self.last_update_time = -999.0
        self.last_inputs = None
        self.cached_expected = None

    def calculate(self, operating_state: dict | None = None, measured_state: dict | None = None) -> dict:
        state = {}
        if operating_state:
            state.update(operating_state)
        if measured_state:
            state.update({k: v for k, v in measured_state.items() if k not in state or state[k] in (None, '')})

        current_time = _safe_float(state.get("time_s"), state.get("timestamp"), 0.0)
        rpm          = _safe_float(state.get("rpm"), 3000.0)
        throttle     = _safe_float(state.get("throttle_pct"), state.get("throttle", 50.0))
        altitude     = _safe_float(state.get("altitude_m"), 0.0)
        ambient_temp = _safe_float(state.get("ambient_temperature_c"), state.get("temperature_c"), 15.0)
        
        # Determine if cache should be updated
        update_needed = True
        if self.cached_expected is not None and self.last_inputs is not None:
            dt = current_time - self.last_update_time
            if 0 <= dt < 1.0:
                # Within max age of 1.0s, check if inputs changed materially
                l_rpm, l_throttle, l_alt, l_amb = self.last_inputs
                if (abs(rpm - l_rpm) < 10.0 and
                    abs(throttle - l_throttle) < 1.0 and
                    abs(altitude - l_alt) < 10.0 and
                    abs(ambient_temp - l_amb) < 1.0):
                    update_needed = False

        if not update_needed:
            # We must still update fast-changing non-RF formulas (like oil pressure and alternator)
            # based on current inputs, but we can reuse the expensive RF outputs
            expected_cht = self.cached_expected["expected_cht"]
            expected_egt = self.cached_expected["expected_egt"]
            expected_oil_temp = self.cached_expected["expected_oil_temperature"]
        else:
            # Build feature array for RF
            X = [[rpm, throttle, altitude, ambient_temp]]
            
            # CHT
            if self.rf_models['cht']:
                expected_cht = float(self.rf_models['cht'].predict(X)[0])
            else:
                expected_cht = (47.9 + 0.000765 * rpm + 0.1020 * throttle - 0.00115 * altitude + 0.632 * ambient_temp)
                
            # EGT
            if self.rf_models['egt']:
                expected_egt = float(self.rf_models['egt'].predict(X)[0])
            else:
                expected_egt = max(ambient_temp, (-12.5 + 0.0248 * rpm + 0.120 * throttle - 0.0012 * altitude + 0.450 * ambient_temp))

            # Oil temperature
            if self.rf_models['oiltemp']:
                expected_oil_temp = float(self.rf_models['oiltemp'].predict(X)[0])
            else:
                expected_oil_temp = (68.5 + 0.00165 * rpm + 0.0650 * throttle + 0.00280 * altitude + 1.21 * ambient_temp)

        self.last_inputs = (rpm, throttle, altitude, ambient_temp)
        self.last_update_time = current_time

        # Fast OLS evaluations that are cheap to run every tick
        actual_oil_temp = _safe_float(state.get("oil_temperature_c"), 100.0)
        pressure     = _safe_float(state.get("pressure_kpa"), state.get("manifold_pressure_kpa"), 101.0)
        air_density  = _safe_float(state.get("air_density_kg_m3"), 1.225)
        torque       = _safe_float(state.get("torque_nm"), 40.0)
        power        = _safe_float(state.get("power_kw"), 15.0)

        # Oil pressure (psi) ?" OLS formulation perfectly handles physical transients and captures viscosity
        viscosity = 0.010 * exp(-0.025 * (actual_oil_temp - 100.0))
        viscosity_ratio = max(0.50, min(2.0, viscosity / 0.010))
        viscosity_factor = 0.75 + 0.25 * viscosity_ratio
        
        rpm_ratio = max(0.0, min(1.50, rpm / 4000.0))
        rpm_pressure = 12.0 * rpm_ratio
        
        expected_oil_pressure = (60.0 + rpm_pressure) * viscosity_factor

        # Fuel flow (kg/s)
        expected_fuel_flow = max(0.00001,
            0.000001 * throttle
            + 0.000000002 * max(0.0, altitude - 1500.0)
        )

        # Vibration (RMS)
        expected_vibration = max(0.0,
            0.135
            + 0.0000045 * rpm
            + 0.00010   * throttle
            + 0.000004  * altitude
        )

        # Alternator power (W)
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
        
        if update_needed:
            self.cached_expected = expected.copy()
            
        return expected
