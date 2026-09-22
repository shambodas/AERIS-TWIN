"""Explainable diagnostic explanations built from engineering evidence."""

from __future__ import annotations


class DiagnosticGenerator:
    def build(self, fault_type: str, severity: str, anomaly_score: float, confidence: float, deviations: dict, sensor_summary: dict, measured: dict = None):
        if measured is None:
            measured = {}
        # Build evidence candidates
        candidates = []
        cht_diff = float(deviations.get("cht_deviation", {}).get("value", 0.0))
        cht_norm = abs(float(deviations.get("cht_deviation", {}).get("normalized", 0.0)))
        if cht_diff > 8.0:
            candidates.append((cht_norm, "CHT above expectation for current operating conditions."))
        elif cht_diff < -8.0:
            candidates.append((cht_norm, "CHT below expectation for current operating conditions."))
            
        egt_diff = float(deviations.get("egt_deviation", {}).get("value", 0.0))
        egt_norm = abs(float(deviations.get("egt_deviation", {}).get("normalized", 0.0)))
        if egt_diff > 8.0:
            candidates.append((egt_norm, "EGT above expectation for current operating conditions."))
        elif egt_diff < -8.0:
            candidates.append((egt_norm, "EGT below expectation for current operating conditions."))

        oil_temp_diff = float(deviations.get("oil_temperature_deviation", {}).get("value", 0.0))
        oil_temp_norm = abs(float(deviations.get("oil_temperature_deviation", {}).get("normalized", 0.0)))
        if oil_temp_diff > 8.0:
            candidates.append((oil_temp_norm, "Oil temperature above expectation for current operating conditions."))
        elif oil_temp_diff < -8.0:
            candidates.append((oil_temp_norm, "Oil temperature below expectation for current operating conditions."))

        oil_press_diff = float(deviations.get("oil_pressure_deviation", {}).get("value", 0.0))
        oil_press_norm = abs(float(deviations.get("oil_pressure_deviation", {}).get("normalized", 0.0)))
        if oil_press_diff < -5.0:
            candidates.append((oil_press_norm, "Oil-pressure deviation indicates pressure loss or degradation."))
        elif oil_press_diff > 5.0:
            candidates.append((oil_press_norm, "Oil-pressure above expectation."))

        vib_abs = abs(float(deviations.get("vibration_deviation", {}).get("absolute", 0.0)))
        if vib_abs > 0.12:
            vib_norm = abs(float(deviations.get("vibration_deviation", {}).get("normalized", 0.0)))
            candidates.append((vib_norm, "Vibration deviates from expected baseline."))

        # Rank by normalized magnitude descending and take top 2
        candidates.sort(key=lambda x: x[0], reverse=True)
        evidence = [c[1] for c in candidates[:2]]

        # Fault-specific interpretations
        interpretations = {
            "EXCESSIVE_VIBRATION": {
                "interpretation": "The system is showing abnormal mechanical/rotational vibration consistent with excessive vibration.",
                "recommended": "Advise inspection of the mechanical/rotational subsystem and continued monitoring / maintenance action."
            },
            "COMBUSTION_INSTABILITY": {
                "interpretation": "The system is showing unstable combustion behaviour.",
                "recommended": "Advise checking combustion/fuel/ignition-related subsystem behaviour."
            },
            "MISFIRE": {
                "interpretation": "The system is showing abnormal combustion consistent with a misfire.",
                "recommended": "Advise inspection of combustion/fuel/ignition system."
            },
            "COOLING_DEGRADATION": {
                "interpretation": "The system is showing degraded cooling performance.",
                "recommended": "Advise checking cooling system and thermal management."
            },
            "OIL_PRESSURE_DEGRADATION": {
                "interpretation": "The system is showing oil-pressure/lubrication degradation.",
                "recommended": "Advise checking lubrication/oil-pressure system."
            },
            "SENSOR_DRIFT": {
                "interpretation": "The system is showing possible sensor measurement drift.",
                "recommended": "Advise sensor validation/calibration/checking."
            },
            "INJECTOR_ABNORMALITY": {
                "interpretation": "The system is showing abnormal fuel-injector behaviour.",
                "recommended": "Advise injector/fuel-delivery inspection."
            },
            "NORMAL": {
                "interpretation": "No strong evidence of abnormal engine behaviour is present in the current telemetry.",
                "recommended": "Continue nominal operation and monitor for drift or persistence."
            }
        }
        
        default_interpretation = "The system is showing sustained observable drift relative to the physics expectation model."
        default_recommended = "Continue monitoring and inspect the most affected subsystem; if degradation persists, perform maintenance checks."
        
        fault_data = interpretations.get(fault_type, {"interpretation": default_interpretation, "recommended": default_recommended})
        interpretation = fault_data["interpretation"]
        recommended = fault_data["recommended"]
        
        # Determine primary signal from maximum normalized deviation
        candidate_signals = [
            ("cht_deviation", "thermal_deviation"),
            ("egt_deviation", "egt_deviation"),
            ("oil_temperature_deviation", "oil_temperature_deviation"),
            ("oil_pressure_deviation", "oil_pressure_deviation"),
            ("fuel_flow_deviation", "fuel_flow_deviation"),
            ("vibration_deviation", "vibration_deviation"),
        ]
        
        best_signal = "vibration_deviation"
        max_norm = -1.0
        
        for dev_key, signal_name in candidate_signals:
            norm = abs(float(deviations.get(dev_key, {}).get("normalized", 0.0)))
            if norm > max_norm:
                max_norm = norm
                best_signal = signal_name
                
        # Include injection timing deviation if significant
        timing_dev = abs(float(measured.get("injection_timing_deviation_deg", 0.0)))
        if timing_dev > 2.0 and (timing_dev / 2.0) > max_norm: # scaling to roughly match normalized features
            best_signal = "injection_timing_deviation"

        return {
            "title": fault_type.replace("_", " ").title() if fault_type != "NORMAL" else "NORMAL ENGINE OPERATION",
            "severity": severity,
            "fault_type": fault_type,
            "confidence": round(float(confidence), 3),
            "primary_signal": best_signal,
            "evidence": evidence,
            "supporting_signals": ["Physics expectation comparison", "Trend persistence", "Cross-sensor consistency"],
            "contradictory_signals": ["No contradictory sensor evidence"] if sensor_summary.get("likely_condition") != "POSSIBLE_SENSOR_FAULT" else ["Single-sensor deviation without sibling support"],
            "interpretation": interpretation,
            "recommended_action": recommended,
            "timestamp": None,
            "persistence_duration": 0.0,
            "anomaly_score": round(float(anomaly_score), 3),
        }
