"""Isolation-Forest-style anomaly detection with a lightweight fallback."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd


class IsolationForestAnomalyDetector:
    def __init__(self, model=None, root_dir: str | Path | None = None):
        self.model = model
        self.root_dir = Path(root_dir) if root_dir is not None else Path(__file__).resolve().parents[1] / "ml" / "model_artifacts"
        self._feature_names = [
            "rpm", "throttle_pct", "altitude_m", "fuel_flow_kg_s",
            "oil_temperature_c", "oil_pressure_psi", "vibration_rms",
            "cht_deviation", "egt_deviation", "oil_temperature_deviation",
            "oil_pressure_deviation", "fuel_flow_deviation", "vibration_deviation"
        ]
        self.metadata = self._load_metadata()
        if "feature_columns" in self.metadata:
            self._feature_names = self.metadata["feature_columns"]

    def _load_metadata(self):
        path = self.root_dir / "model_metadata.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (TypeError, ValueError):
            return {}

    def _score_from_model(self, features: dict) -> float | None:
        if self.model is None:
            return None
        try:
            row = pd.DataFrame([[float(features.get(name, 0.0)) for name in self._feature_names]], columns=self._feature_names)
            decision = float(self.model.decision_function(row)[0])
            score = 1.0 / (1.0 + math.exp(-decision))
            return float(min(1.0, max(0.0, score)))
        except Exception:
            return None

    def _apply_deterministic_guards(self, features: dict, base_score: float) -> float:
        safety_score = base_score
        
        # Deterministic Safety Overrides
        if abs(features.get("cht_deviation", 0.0)) > 24.0 or abs(features.get("egt_deviation", 0.0)) > 36.0:
            safety_score = max(safety_score, 0.4)
        
        if abs(features.get("vibration_deviation", 0.0)) > 0.30 or float(features.get("vibration_rms", 0.0)) > 0.6:
            safety_score = max(safety_score, 0.60)
            
        return safety_score

    def score(self, features: dict) -> float:
        model_score = self._score_from_model(features)
        
        if model_score is None:
            scales = {
                "cht_deviation": 12.0,
                "egt_deviation": 18.0,
                "oil_temperature_deviation": 12.0,
                "oil_pressure_deviation": 8.0,
                "fuel_flow_deviation": 0.00035,
                "vibration_deviation": 0.12,
            }
            directional = {
                "cht_deviation": 1.0,
                "egt_deviation": 1.0,
                "oil_temperature_deviation": 1.0,
                "oil_pressure_deviation": -1.0,
            }
            normalized = []
            for name, scale in scales.items():
                value = float(features.get(name, 0.0))
                if name in directional:
                    value *= directional[name]
                    normalized.append(max(0.0, value / scale - 1.0))
                else:
                    normalized.append(max(0.0, abs(value) / scale - 1.0))
            if normalized:
                base_score = min(1.0, max(0.0, sum(normalized) / len(normalized)))
            else:
                base_score = 0.0
        else:
            base_score = model_score

        safety_score = self._apply_deterministic_guards(features, base_score)
        return float(min(1.0, max(0.0, safety_score)))

    def detect(self, features: dict) -> dict:
        final_score = self.score(features)
        return {
            "score": final_score,
            "is_anomaly": final_score > 0.55,
            "normalized_score": final_score,
            "threshold": 0.55,
        }
