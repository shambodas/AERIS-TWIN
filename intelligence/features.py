"""Feature engineering for anomaly and fault inference."""

from __future__ import annotations

from math import isnan

from intelligence.temporal_features import TemporalFeatureBuilder


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


class FeatureEngineer:
    def __init__(self):
        self.temporal = TemporalFeatureBuilder()

    def build(self, expected: dict, measured: dict, deviations: dict, history=None):
        features = {
            "rpm": _safe_float(measured.get("rpm"), 0.0),
            "throttle_pct": _safe_float(measured.get("throttle_pct"), measured.get("throttle", 0.0)),
            "altitude_m": _safe_float(measured.get("altitude_m"), 0.0),
            "ambient_temperature_c": _safe_float(measured.get("ambient_temperature_c"), 15.0),
            "pressure_kpa": _safe_float(measured.get("pressure_kpa"), measured.get("manifold_pressure_kpa", 101.0)),
            "fuel_flow_kg_s": _safe_float(measured.get("fuel_flow"), measured.get("fuel_flow_kg_s", 0.0)),
            "oil_temperature_c": _safe_float(measured.get("oil_temperature_c"), 0.0),
            "oil_pressure_psi": _safe_float(measured.get("oil_pressure_psi"), 0.0),
            "vibration_rms": _safe_float(measured.get("vibration_rms"), 0.0),
            "torque_nm": _safe_float(measured.get("torque_nm"), 0.0),
            "power_kw": _safe_float(measured.get("power_kw"), 0.0),
            "engine_load_pct": _safe_float(measured.get("engine_load_pct"), measured.get("load_pct", 0.0)),
            "expected_cht": _safe_float(expected.get("expected_cht"), 0.0),
            "expected_egt": _safe_float(expected.get("expected_egt"), 0.0),
            "expected_oil_temperature": _safe_float(expected.get("expected_oil_temperature"), 0.0),
            "expected_oil_pressure": _safe_float(expected.get("expected_oil_pressure"), 0.0),
            "expected_fuel_flow": _safe_float(expected.get("expected_fuel_flow"), 0.0),
            "expected_vibration": _safe_float(expected.get("expected_vibration"), 0.0),
            "cht_deviation": _safe_float(deviations.get("cht_deviation", {}).get("value"), 0.0),
            "egt_deviation": _safe_float(deviations.get("egt_deviation", {}).get("value"), 0.0),
            "oil_temperature_deviation": _safe_float(deviations.get("oil_temperature_deviation", {}).get("value"), 0.0),
            "oil_pressure_deviation": _safe_float(deviations.get("oil_pressure_deviation", {}).get("value"), 0.0),
            "fuel_flow_deviation": _safe_float(deviations.get("fuel_flow_deviation", {}).get("value"), 0.0),
            "vibration_deviation": _safe_float(deviations.get("vibration_deviation", {}).get("value"), 0.0),
            "alternator_power_deviation": _safe_float(deviations.get("alternator_power_deviation", {}).get("value"), 0.0),
            "injection_timing_deviation_deg": _safe_float(measured.get("injection_timing_deviation_deg"), 0.0),
            "thermal_deviation_consistency": abs(_safe_float(deviations.get("cht_deviation", {}).get("absolute"), 0.0)) + abs(_safe_float(deviations.get("egt_deviation", {}).get("absolute"), 0.0)),
            "cross_sensor_alignment": abs(_safe_float(deviations.get("cht_deviation", {}).get("absolute"), 0.0)) / max(1.0, abs(_safe_float(deviations.get("oil_temperature_deviation", {}).get("absolute"), 0.0)) + 1e-9),
        }
        features = self.temporal.build(history=history or [], current_features=features)
        return features
