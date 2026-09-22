"""Observable health scoring based on deviations and anomaly evidence."""

from __future__ import annotations


class HealthScore:
    def compute(self, anomaly_score: float, fault_confidence: float, deviations: dict, sensor_summary: dict, persistence: float = 0.0, fault_type: str = "NORMAL"):
        score = 100.0
        score -= anomaly_score * 40.0
        if fault_type != "NORMAL":
            score -= fault_confidence * 20.0
        cht_deviation = float(deviations.get("cht_deviation", {}).get("value", 0.0))
        egt_deviation = float(deviations.get("egt_deviation", {}).get("value", 0.0))
        oil_pressure_deviation = float(deviations.get("oil_pressure_deviation", {}).get("value", 0.0))
        score -= max(0.0, cht_deviation - 12.0) * 0.35
        score -= max(0.0, egt_deviation - 18.0) * 0.25
        score -= max(0.0, -oil_pressure_deviation - 8.0) * 0.6
        score -= max(0.0, abs(float(deviations.get("vibration_deviation", {}).get("absolute", 0.0))) - 0.12) * 18.0
        score -= persistence * 10.0
        if sensor_summary.get("likely_condition") == "POSSIBLE_SENSOR_FAULT":
            score -= 8.0
        score = max(0.0, min(100.0, score))
        if score >= 90:
            severity = "NORMAL"
        elif score >= 75:
            severity = "INFORMATION"
        elif score >= 50:
            severity = "WARNING"
        elif score >= 25:
            severity = "CRITICAL"
        else:
            severity = "SEVERE"
        return {"score": round(score, 2), "severity": severity}
