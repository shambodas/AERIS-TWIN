"""Reasoned separation of engine faults from sensor faults."""

from __future__ import annotations


class SensorFaultArbitrator:
    def assess(self, measured: dict, expected: dict, deviations: dict, features: dict = None) -> dict:
        def get_signed(dev_dict):
            val = abs(float(dev_dict.get("absolute", 0.0)))
            return -val if dev_dict.get("direction") == "NEGATIVE" else val

        cht_dev = get_signed(deviations.get("cht_deviation", {}))
        egt_dev = get_signed(deviations.get("egt_deviation", {}))
        oil_temp_dev = get_signed(deviations.get("oil_temperature_deviation", {}))
        oil_pressure_dev = get_signed(deviations.get("oil_pressure_deviation", {}))
        
        vibration_dev = abs(float(deviations.get("vibration_deviation", {}).get("absolute", 0.0)))

        cht_channels = [
            float(measured.get(f"cht_cylinder_{index}_c", 0.0))
            for index in range(1, 5)
        ]
        isolated_cht_outlier = max(cht_channels) - min(cht_channels) > 12.0
        
        engine_evidence = 0.0
        sensor_evidence = 0.0

        # Check independent physical evidence of a real engine event (e.g. injector/fuel/timing faults)
        injection_timing_dev = abs(float(measured.get("injection_timing_deviation_deg", 0.0)))
        fuel_flow_norm = abs(float(deviations.get("fuel_flow_deviation", {}).get("normalized", 0.0)))
        has_physical_propulsion_evidence = (injection_timing_dev > 2.0) or (fuel_flow_norm > 3.0)

        # Sensor faults: Unphysical signed deviations or isolated outliers
        if isolated_cht_outlier and vibration_dev < 0.15:
            if not has_physical_propulsion_evidence:
                sensor_evidence += 1.0
            
        # If a single parameter drifts heavily but related parameters are completely stable
        if not isolated_cht_outlier and abs(cht_dev) > 12.0 and abs(egt_dev) < 5.0 and abs(oil_temp_dev) < 5.0 and abs(oil_pressure_dev) < 3.0 and vibration_dev < 0.12:
            sensor_evidence += 1.0
            
        # Unphysical directions (engines overheat, they don't magically freeze; oil pressure drops, it doesn't magically spike)
        engine_is_warm = max(cht_channels) > 50.0 or float(measured.get("oil_temperature_c", 0.0)) > 50.0
        
        cht_roc = float(features.get("cht_deviation_rate_of_change", 0.0)) if features else 0.0
        egt_roc = float(features.get("egt_deviation_rate_of_change", 0.0)) if features else 0.0
        oil_temp_roc = float(features.get("oil_temperature_deviation_rate_of_change", 0.0)) if features else 0.0
        
        cht_rolling = float(features.get("cht_deviation_rolling_mean", cht_dev)) if features else cht_dev
        egt_rolling = float(features.get("egt_deviation_rolling_mean", egt_dev)) if features else egt_dev
        oil_rolling = float(features.get("oil_temperature_deviation_rolling_mean", oil_temp_dev)) if features else oil_temp_dev

        def is_implausible_drop(dev, roc, rolling, threshold, is_warm):
            if dev >= threshold:
                return False
            has_history = abs(roc) > 1e-5 or abs(rolling - dev) > 1e-5
            if has_history:
                if roc < -5.0: return True
                if rolling > (threshold * 0.5): return True
            return False

        if is_implausible_drop(cht_dev, cht_roc, cht_rolling, -30.0, engine_is_warm):
            sensor_evidence += 1.5
        if is_implausible_drop(egt_dev, egt_roc, egt_rolling, -40.0, engine_is_warm):
            sensor_evidence += 1.5
        if is_implausible_drop(oil_temp_dev, oil_temp_roc, oil_rolling, -40.0, engine_is_warm):
            sensor_evidence += 1.5
        if oil_pressure_dev > 30.0: # Oil pressure spiked
            sensor_evidence += 1.5

        # Engine faults: Correlated physical degradation
        if not isolated_cht_outlier and cht_dev > 10.0 and egt_dev > 10.0 and oil_temp_dev > 8.0:
            engine_evidence += 1.0
            
        if oil_pressure_dev < -8.0 and abs(float(measured.get("rpm", 0.0)) - float(expected.get("expected_rpm", 0.0))) < 200.0:
            engine_evidence += 0.7
            
        if vibration_dev > 0.15 and abs(float(measured.get("rpm", 0.0)) - float(expected.get("expected_rpm", 0.0))) < 250.0:
            engine_evidence += 0.8

        if sensor_evidence > engine_evidence:
            likely_condition = "POSSIBLE_SENSOR_FAULT"
        elif engine_evidence > sensor_evidence:
            likely_condition = "POSSIBLE_ENGINE_FAULT"
        else:
            likely_condition = "AMBIGUOUS"

        return {
            "engine_fault_evidence": round(engine_evidence, 3),
            "sensor_fault_evidence": round(sensor_evidence, 3),
            "ambiguous_evidence": max(0.0, abs(engine_evidence - sensor_evidence)),
            "likely_condition": likely_condition,
        }
