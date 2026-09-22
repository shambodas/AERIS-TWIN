"""Deviation and normalization utilities."""

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


def compute_deviations(expected: dict, measured: dict) -> dict:
    scales = {
        "cht": 12.0,
        "egt": 18.0,
        "oil_temperature": 12.0,
        "oil_pressure": 8.0,
        "fuel_flow": 0.00035,
        "vibration": 0.12,
        "alternator_power": 50.0,
    }
    
    meas_mapped = {
        "cht": max(
            _safe_float(measured.get("cht_cylinder_1_c")),
            _safe_float(measured.get("cht_cylinder_2_c")),
            _safe_float(measured.get("cht_cylinder_3_c")),
            _safe_float(measured.get("cht_cylinder_4_c"))
        ) if "cht_cylinder_1_c" in measured else _safe_float(measured.get("cht")),
        "egt": max(
            _safe_float(measured.get("egt_cylinder_1_c")),
            _safe_float(measured.get("egt_cylinder_2_c")),
            _safe_float(measured.get("egt_cylinder_3_c")),
            _safe_float(measured.get("egt_cylinder_4_c"))
        ) if "egt_cylinder_1_c" in measured else _safe_float(measured.get("egt")),
        "oil_temperature": _safe_float(measured.get("oil_temperature_c")),
        "oil_pressure": _safe_float(measured.get("oil_pressure_psi")),
        "fuel_flow": _safe_float(measured.get("fuel_flow_kg_s")),
        "vibration": _safe_float(measured.get("vibration_rms")),
        "alternator_power": _safe_float(measured.get("alternator_power_w")),
    }

    deviations = {}

    for key, expected_key in {
        "cht_deviation": ("expected_cht", "cht"),
        "egt_deviation": ("expected_egt", "egt"),
        "oil_temperature_deviation": ("expected_oil_temperature", "oil_temperature"),
        "oil_pressure_deviation": ("expected_oil_pressure", "oil_pressure"),
        "fuel_flow_deviation": ("expected_fuel_flow", "fuel_flow"),
        "vibration_deviation": ("expected_vibration", "vibration"),
        "alternator_power_deviation": ("expected_alternator_power_w", "alternator_power"),
    }.items():
        exp = _safe_float(expected.get(expected_key[0]), 0.0)

        meas = meas_mapped.get(expected_key[1], 0.0)
        diff = meas - exp
        absolute = abs(diff)
        scale = scales[expected_key[1]]
        normalized = diff / scale if abs(scale) > 1e-9 else 0.0
        
        denominator = exp if abs(exp) >= abs(scale) else scale
        pct = (absolute / abs(denominator) * 100.0) if abs(denominator) > 1e-9 else 0.0
        
        deviations[key] = {
            "value": float(diff),
            "absolute": float(absolute),
            "normalized": float(normalized),
            "percent": float(pct),
            "direction": "POSITIVE" if diff > 0 else "NEGATIVE" if diff < 0 else "ZERO",
            "magnitude": float(absolute),
        }
    return deviations
