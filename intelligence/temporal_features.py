"""Temporal rolling features for trend-aware analytics."""

from __future__ import annotations

import math
from statistics import mean, pstdev


class TemporalFeatureBuilder:
    def build(self, history, current_features):
        output = dict(current_features)
        if not history:
            for name in ["rolling_mean", "rolling_std", "rate_of_change", "slope", "persistence"]:
                output[name] = 0.0
            return output

        recent = list(history)[-10:]
        for key in ["cht_deviation", "egt_deviation", "oil_temperature_deviation", "oil_pressure_deviation", "fuel_flow_deviation", "vibration_deviation"]:
            values = [row.get("features", {}).get(key, 0.0) for row in recent if row.get("features")]
            if not values:
                values = [current_features.get(key, 0.0)]
            output[f"{key}_rolling_mean"] = sum(values) / len(values)
            output[f"{key}_rolling_std"] = pstdev(values) if len(values) > 1 else 0.0
            if len(values) >= 2:
                output[f"{key}_rate_of_change"] = (values[-1] - values[0]) / max(len(values) - 1, 1)
                output[f"{key}_slope"] = (values[-1] - values[0]) / max(len(values) - 1, 1)
            else:
                output[f"{key}_rate_of_change"] = 0.0
                output[f"{key}_slope"] = 0.0
            output[f"{key}_persistence"] = min(1.0, max(0.0, abs(output[f"{key}_rolling_mean"]) / max(1.0, abs(current_features.get(key, 0.0)) + 1e-9)))
        return output
