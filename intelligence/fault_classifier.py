"""Random-Forest-style fault classifier using observable engineering signals."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


class RandomForestFaultClassifier:
    def __init__(self, model=None, root_dir: str | Path | None = None):
        self.model = model
        self.root_dir = Path(root_dir) if root_dir is not None else Path(__file__).resolve().parents[1] / "ml" / "model_artifacts"
        self.classes = [
            "NORMAL",
            "COOLING_DEGRADATION",
            "EXCESSIVE_VIBRATION",
            "MISFIRE",
            "OIL_PRESSURE_DEGRADATION",
            "COMBUSTION_INSTABILITY",
            "SENSOR_DRIFT",
        ]
        self.metadata = self._load_metadata()

    def _load_metadata(self):
        path = self.root_dir / "model_metadata.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (TypeError, ValueError):
            return {}

    def _predict_from_model(self, features: dict):
        if self.model is None:
            return None
        try:
            feature_names = self.metadata.get("feature_columns", [])
            if not feature_names:
                return None
            row = pd.DataFrame([[float(features.get(name, 0.0)) for name in feature_names]], columns=feature_names)
            prediction = self.model.predict(row)[0]
            if isinstance(prediction, (int, float)):
                prediction = {
                    0: "NORMAL", 1: "MISFIRE", 2: "COOLING_DEGRADATION",
                    3: "COMBUSTION_INSTABILITY", 4: "SENSOR_DRIFT", 5: "OIL_PRESSURE_DEGRADATION",
                    6: "EXCESSIVE_VIBRATION"
                }.get(int(prediction), "UNKNOWN")
            
            ui_mapping = {}
            predicted_str = str(prediction)
            canonical_prediction = ui_mapping.get(predicted_str, predicted_str)
            
            probabilities = self.model.predict_proba(row)[0]
            classes = getattr(self.model, "classes_", self.classes)
            prob_map = {ui_mapping.get(str(cls), str(cls)): float(prob) for cls, prob in zip(classes, probabilities)}
            return {"fault_type": canonical_prediction, "confidence": float(max(probabilities)), "probabilities": prob_map}
        except Exception:
            return None

    def predict(self, features: dict) -> dict:
        model_prediction = self._predict_from_model(features)
        if model_prediction is not None:
            return model_prediction

        cht_signed = float(features.get("cht_deviation", 0.0))
        egt_signed = float(features.get("egt_deviation", 0.0))
        oil_temperature_signed = float(features.get("oil_temperature_deviation", 0.0))
        cht = abs(cht_signed)
        egt = abs(egt_signed)
        oil_temperature = abs(oil_temperature_signed)
        oil_pressure_signed = float(features.get("oil_pressure_deviation", 0.0))
        oil_pressure = abs(oil_pressure_signed)
        vibration = abs(float(features.get("vibration_deviation", 0.0)))
        fuel = abs(float(features.get("fuel_flow_deviation", 0.0)))
        thermal = cht + egt

        if vibration > 0.25 and egt_signed < -40.0:
            predicted = "MISFIRE"
            confidence = 0.78
        elif vibration > 0.85:
            predicted = "MISFIRE"
            confidence = 0.78
        elif vibration > 0.25:
            predicted = "EXCESSIVE_VIBRATION"
            confidence = 0.76
        elif oil_pressure_signed < -2.0 and vibration < 0.25:
            predicted = "OIL_PRESSURE_DEGRADATION"
            confidence = 0.74
        elif cht_signed > 12.0 and egt < 6.0 and oil_temperature < 6.0 and oil_pressure < 4.0 and vibration < 0.15:
            predicted = "SENSOR_DRIFT"
            confidence = 0.72
        elif max(cht_signed, egt_signed) > 10.0 and oil_pressure < 5.0:
            predicted = "COOLING_DEGRADATION"
            confidence = 0.78
        elif max(cht_signed, egt_signed) > 15.0:
            predicted = "COOLING_DEGRADATION"
            confidence = 0.72
        else:
            predicted = "NORMAL"
            confidence = 0.6

        confidence = min(confidence, 1.0)
        probs = {cls: 0.05 for cls in self.classes}
        if predicted in probs:
            probs[predicted] = confidence
        total = sum(probs.values())
        probs = {k: (v / total) for k, v in probs.items()}
        return {"fault_type": predicted, "confidence": float(confidence), "probabilities": probs}
