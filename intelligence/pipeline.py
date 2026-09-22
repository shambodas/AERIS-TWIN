"""Central intelligence pipeline integrating expectation, deviation, ML, and health scoring."""

from __future__ import annotations

import joblib
import numpy as np
from pathlib import Path
from typing import Optional

from intelligence.anomaly_detector import IsolationForestAnomalyDetector
from intelligence.deviations import compute_deviations
from intelligence.diagnostics import DiagnosticGenerator
from intelligence.fault_classifier import RandomForestFaultClassifier
from intelligence.features import FeatureEngineer
from intelligence.health_score import HealthScore
from intelligence.physics_expectation import PhysicsExpectationEngine
from intelligence.sensor_fault_arbitration import SensorFaultArbitrator
from intelligence.severity import SeverityEngine
from intelligence.thermal_diagnostics import ThermalDiagnostics
from ml.model_store import ModelStore

# RUL Model D feature order — must match training exactly
_RUL_FEATURES = [
    "measured_rpm",
    "measured_manifold_pressure_kpa",
    "measured_intake_temperature_c",
    "measured_fuel_flow_kg_s",
    "measured_torque_nm",
    "measured_power_kw",
    "measured_cht_cylinder_1_c",
    "measured_cht_cylinder_2_c",
    "measured_cht_cylinder_3_c",
    "measured_cht_cylinder_4_c",
    "measured_egt_cylinder_1_c",
    "measured_egt_cylinder_2_c",
    "measured_egt_cylinder_3_c",
    "measured_egt_cylinder_4_c",
    "measured_oil_temperature_c",
    "measured_oil_pressure_psi",
    "measured_oil_flow_l_min",
    "measured_battery_voltage_v",
    "measured_battery_current_a",
    "measured_battery_soc",
    "measured_vibration_rms",
    "measured_vibration_peak",
    "measured_vibration_0_5x",
    "measured_vibration_1x",
    "measured_vibration_2x",
]


class IntelligencePipeline:
    def __init__(self, root_dir: str | Path | None = None):
        self.ml_enabled = __import__("os").getenv("AERIS_ENABLE_ML", "1").lower() in {"1", "true", "yes"}
        self.model_store = None
        self.expectation_engine = PhysicsExpectationEngine()
        self.feature_engineer = FeatureEngineer()
        self.model_store = self._load_model_store(root_dir)
        self.anomaly_detector = IsolationForestAnomalyDetector(model=self.model_store["anomaly_model"] if self.model_store else None, root_dir=root_dir)
        self.fault_classifier = RandomForestFaultClassifier(model=self.model_store["fault_model"] if self.model_store else None, root_dir=root_dir)
        self.sensor_arbitrator = SensorFaultArbitrator()
        self.health_score = HealthScore()
        self.severity_engine = SeverityEngine()
        self.diagnostics = DiagnosticGenerator()
        self.thermal_diagnostics = ThermalDiagnostics()
        self.history = []
        self.runtime_mode = "MACHINE_LEARNING" if self.ml_enabled and self.model_store is not None else "FALLBACK_INTELLIGENCE"
        # Load RUL model (Model D — physics only, no elapsed time)
        self._rul_model = self._load_rul_model(root_dir)
        self.reset_rul_state()

    def reset_history(self):
        self.history.clear()

    def reset_rul_state(self):
        self._min_rul_served_this_session = float('inf')
        self._rul_buffer = []

    def _load_rul_model(self, root_dir) -> Optional[object]:
        """Load trained RUL Model D artifact. Returns None if not found."""
        model_root = (
            Path(root_dir) if root_dir is not None
            else Path(__file__).resolve().parents[1] / "ml" / "model_artifacts"
        )
        rul_path = model_root / "rul_model_d.pkl"
        if rul_path.exists():
            try:
                return joblib.load(rul_path)
            except Exception:
                return None
        return None

    def _predict_rul(self, measured_state) -> dict:
        """Run RUL inference using Model D (physics sensors only, no elapsed time)."""
        if self._rul_model is None:
            return {
                "available": False,
                "estimated_rul": None,
                "confidence": 0.0,
                "status": "EXPERIMENTAL",
                "reason": "RUL model not loaded.",
            }
        try:
            row = [
                getattr(measured_state, feat.removeprefix("measured_"), 0.0) or 0.0
                for feat in _RUL_FEATURES
            ]
            X = np.array(row, dtype=float).reshape(1, -1)
            raw_rul_seconds = float(self._rul_model.predict(X)[0])
            raw_rul_seconds = max(0.0, raw_rul_seconds)  # RUL >= 0
            
            self._rul_buffer.append(raw_rul_seconds)
            if len(self._rul_buffer) > 3:
                self._rul_buffer.pop(0)
            
            filtered_rul = float(np.median(self._rul_buffer))

            return {
                "available": True,
                "estimated_rul": filtered_rul,
                "raw_estimated_rul": raw_rul_seconds,
                "filtered_estimated_rul": filtered_rul,
                "confidence": None,   # No validated uncertainty method — see RUL_VALIDATION_REPORT.txt
                "status": "EXPERIMENTAL",
                "reason": "Model D predicts accelerated simulation seconds. Not real-world engine hours.",
            }
        except Exception as exc:
            return {
                "available": False,
                "estimated_rul": None,
                "confidence": 0.0,
                "status": "EXPERIMENTAL",
                "reason": f"RUL inference error: {exc}",
            }

    def _load_model_store(self, root_dir):
        if root_dir is None and not self.ml_enabled:
            return None
        model_root = Path(root_dir) if root_dir is not None else Path(__file__).resolve().parents[1] / "ml" / "model_artifacts"
        try:
            store = ModelStore(root_dir=model_root)
            bundle = store.load_bundle()
            expected = set(self.anomaly_detector_features())
            if set(bundle.get("metadata", {}).get("feature_columns", [])) != expected:
                return None
            return bundle
        except (FileNotFoundError, ValueError):
            return None

    @staticmethod
    def anomaly_detector_features():
        return ModelStore.RUNTIME_FEATURES
    def _normalize_measured(self, true_state, measured_state):
        state = {}
        if true_state is not None:
            for key, value in getattr(true_state, '__dict__', {}).items():
                if value is not None:
                    state[key] = value
        if measured_state is not None:
            for key, value in getattr(measured_state, '__dict__', {}).items():
                if value is not None:
                    state[key] = value
        if not state:
            return {}
        return state

    def _extract_metrics(self, true_state, measured_state):
        metrics = {}
        if true_state is not None:
            for key in ["rpm", "altitude_m", "airspeed_mps", "throttle_pct", "time_s", "power_kw", "torque_nm", "fuel_flow_kg_s", "oil_pressure_psi", "vibration_rms", "cht_c", "egt_c", "oil_temperature_c", "ambient_temperature_c", "air_density_kg_m3", "manifold_pressure_kpa", "intake_temperature_c"]:
                if hasattr(true_state, key):
                    metrics[key] = getattr(true_state, key)
        if measured_state is not None:
            for key in ["rpm", "manifold_pressure_kpa", "oil_temperature_c", "oil_pressure_psi", "fuel_flow_kg_s", "vibration_rms", "power_kw", "torque_nm", "cht_cylinder_1_c", "cht_cylinder_2_c", "cht_cylinder_3_c", "cht_cylinder_4_c", "egt_cylinder_1_c", "egt_cylinder_2_c", "egt_cylinder_3_c", "egt_cylinder_4_c", "alternator_power_w", "injection_timing_deviation_deg"]:
                if hasattr(measured_state, key):
                    metrics[key] = getattr(measured_state, key)
        return metrics

    def invalidate_cache(self):
        """Force the next process() call to run a full pipeline evaluation.
        Call this whenever external state changes (e.g. fault injection, reset)
        that must be reflected immediately regardless of the simulated-time cache window.
        """
        if hasattr(self, 'last_process_time'):
            del self.last_process_time
        if hasattr(self, 'last_record'):
            del self.last_record
        if hasattr(self, 'expectation'):
            self.expectation.invalidate_cache()

    def process(self, true_state, measured_state, timestamp=None, fault_context: str | None = None):
        """Execute the full intelligence pipeline on incoming telemetry."""
        ts = timestamp if timestamp is not None else 0.0
        # CACHE: Run full intelligence only every 1.0s of simulated time so the
        # fast-physics loop can advance without re-running the expensive RF models
        # every step. Cache is invalidated explicitly on fault injection / reset.
        if hasattr(self, 'last_process_time') and hasattr(self, 'last_record'):
            dt = ts - self.last_process_time
            if 0 <= dt < 1.0:
                return self.last_record

        self.last_process_time = ts
        metrics = self._extract_metrics(true_state, measured_state)

        def clean(value, fallback=0.0):
            try:
                if value is None:
                    return float(fallback)
                value = float(value)
                if value != value or value in (float('inf'), float('-inf')):
                    return float(fallback)
                return value
            except (TypeError, ValueError):
                return float(fallback)

        measured = {
            "rpm": clean(metrics.get("rpm", 0.0)),
            "throttle_pct": clean(getattr(true_state, "throttle_pct", 50.0) if true_state is not None else 50.0),
            "altitude_m": clean(getattr(true_state, "altitude_m", 0.0) if true_state is not None else 0.0),
            "time_s": clean(getattr(true_state, "time_s", timestamp if timestamp is not None else 0.0) if true_state is not None else timestamp or 0.0),
            "ambient_temperature_c": clean(getattr(true_state, "ambient_temperature_c", 15.0) if true_state is not None else 15.0),
            "pressure_kpa": clean(getattr(true_state, "manifold_pressure_kpa", 101.0) if true_state is not None else 101.0),
            "air_density_kg_m3": clean(getattr(true_state, "air_density_kg_m3", 1.225) if true_state is not None else 1.225),
            "engine_load_pct": clean(getattr(true_state, "power_kw", 0.0) if true_state is not None else 0.0),
            "cht": clean(max(
                float(metrics.get("cht_cylinder_1_c", 0.0) or 0.0),
                float(metrics.get("cht_cylinder_2_c", 0.0) or 0.0),
                float(metrics.get("cht_cylinder_3_c", 0.0) or 0.0),
                float(metrics.get("cht_cylinder_4_c", 0.0) or 0.0)
            )),
            "egt": clean(max(
                float(metrics.get("egt_cylinder_1_c", 0.0) or 0.0),
                float(metrics.get("egt_cylinder_2_c", 0.0) or 0.0),
                float(metrics.get("egt_cylinder_3_c", 0.0) or 0.0),
                float(metrics.get("egt_cylinder_4_c", 0.0) or 0.0)
            )),
            "oil_temperature_c": clean(metrics.get("oil_temperature_c", 0.0)),
            "oil_temperature": clean(metrics.get("oil_temperature_c", 0.0)),
            "oil_pressure_psi": clean(metrics.get("oil_pressure_psi", 0.0)),
            "fuel_flow": clean(metrics.get("fuel_flow_kg_s", 0.0)),
            "vibration": clean(metrics.get("vibration_rms", 0.0)),
            "torque_nm": clean(metrics.get("torque_nm", 0.0)),
            "power_kw": clean(metrics.get("power_kw", 0.0)),
            "fuel_flow_kg_s": clean(metrics.get("fuel_flow_kg_s", 0.0)),
            "load_pct": clean(metrics.get("engine_load_pct", 0.0)),
            "manifold_pressure_kpa": clean(metrics.get("manifold_pressure_kpa", 101.0)),
            "oil_pressure": clean(metrics.get("oil_pressure_psi", 0.0)),
            "vibration_rms": clean(metrics.get("vibration_rms", 0.0)),
            "alternator_power_w": clean(metrics.get("alternator_power_w", 0.0)),
            "injection_timing_deviation_deg": clean(metrics.get("injection_timing_deviation_deg", 0.0)),
        }
        for channel in (
            "cht_cylinder_1_c", "cht_cylinder_2_c", "cht_cylinder_3_c", "cht_cylinder_4_c",
            "egt_cylinder_1_c", "egt_cylinder_2_c", "egt_cylinder_3_c", "egt_cylinder_4_c",
        ):
            measured[channel] = clean(metrics.get(channel, 0.0))
        operating_state = {
            "rpm": measured.get("rpm", 0.0),
            "throttle_pct": measured.get("throttle_pct", 50.0),
            "altitude_m": measured.get("altitude_m", 0.0),
            "time_s": measured.get("time_s", 0.0),
            "ambient_temperature_c": measured.get("ambient_temperature_c", 15.0),
            "pressure_kpa": measured.get("pressure_kpa", 101.0),
            "air_density_kg_m3": measured.get("air_density_kg_m3", 1.225),
            "load_pct": measured.get("engine_load_pct", 50.0),
            "torque_nm": measured.get("torque_nm", 0.0),
            "power_kw": measured.get("power_kw", 0.0),
        }
        expected = self.expectation_engine.calculate(operating_state=operating_state, measured_state=measured)
        deviations = compute_deviations(expected, measured)
        features = self.feature_engineer.build(expected, measured, deviations, history=self.history)

        anomaly = self.anomaly_detector.detect(features)
        fault_classification = self.fault_classifier.predict(features)
        with open('debug.log', 'a') as f:
            f.write(f"t={ts:.1f} cht={measured.get('cht_cylinder_1_c')} exp_cht={expected.get('expected_cht')} dev={features.get('cht_deviation')} => {fault_classification['fault_type']}\n")
            
        sensor_summary = self.sensor_arbitrator.assess(measured, expected, deviations, features)
        strong_physical_evidence = False
        if fault_classification["fault_type"] not in ("NORMAL", "SENSOR_DRIFT"):
            if fault_classification["confidence"] > 0.85:
                strong_physical_evidence = True
            elif abs(float(measured.get("injection_timing_deviation_deg", 0.0))) > 2.0:
                strong_physical_evidence = True
            elif abs(float(deviations.get("fuel_flow_deviation", {}).get("normalized", 0.0))) > 3.0:
                strong_physical_evidence = True

        if (
            sensor_summary["likely_condition"] == "POSSIBLE_SENSOR_FAULT"
            and sensor_summary["sensor_fault_evidence"] >= 1.0
            and not strong_physical_evidence
        ):
            fault_classification = {
                "fault_type": "SENSOR_DRIFT",
                "confidence": min(1.0, max(0.5, float(sensor_summary["sensor_fault_evidence"]))),
                "probabilities": {"SENSOR_DRIFT": 1.0},
            }

        recent_scores = [abs(float(row.get("anomaly", {}).get("score", 0.0))) for row in self.history[-30:] if "anomaly" in row]
        recent_scores.append(abs(float(anomaly["score"])))
        persistence = min(1.0, max(0.0, (sum(recent_scores) / len(recent_scores)) * 1.5))
        health = self.health_score.compute(
            anomaly_score=anomaly["score"] if anomaly["is_anomaly"] else 0.0,
            fault_confidence=fault_classification["confidence"],
            deviations=deviations,
            sensor_summary=sensor_summary,
            persistence=persistence,
            fault_type=fault_classification["fault_type"],
        )
        affected_channels = sum(
            abs(float(item.get("normalized", 0.0))) >= 1.0
            for item in deviations.values()
        )
        # A confirmed non-NORMAL classification (based on observable residuals and features)
        # provides independent evidence of an engine anomaly, even when the Isolation Forest's
        # binary is_anomaly flag is False (the IF threshold is conservative).
        # Including the anomaly score in this case allows severity to reflect the full
        # observable evidence; no hidden simulator state is used.
        _has_fault_signal = anomaly["is_anomaly"] or fault_classification["fault_type"] != "NORMAL"
        severity = self.severity_engine.assess(
            float(health["score"]),
            float(anomaly["score"]) if _has_fault_signal else 0.0,
            persistence=persistence if _has_fault_signal else 0.0,
            affected_channels=max(1, affected_channels),
        )
        diagnosis = self.diagnostics.build(fault_classification["fault_type"], severity, anomaly["score"], fault_classification["confidence"], deviations, sensor_summary, measured)
        
        # Add conflict flag if severity is high but classification is NORMAL (or overridden to NORMAL)
        if fault_classification["fault_type"] == "NORMAL" and severity in ("CRITICAL", "SEVERE"):
            diagnosis["classification_conflict"] = True
            diagnosis["title"] = "UNCLASSIFIED ABNORMALITY"
            diagnosis["interpretation"] = "Abnormal engine behaviour detected; fault classification is uncertain."
            diagnosis["recommended_action"] = "Perform immediate maintenance checks."
        elif fault_classification["fault_type"] == "NORMAL" and severity == "WARNING" and anomaly.get("is_anomaly", False):
            diagnosis["classification_conflict"] = True
            diagnosis["title"] = "UNCLASSIFIED ABNORMALITY"
            diagnosis["interpretation"] = "Engine behaviour is diverging from expected conditions; fault classification is uncertain."
            diagnosis["recommended_action"] = "Continue monitoring and perform checks."
        else:
            diagnosis["classification_conflict"] = False

        thermal_history = [item["measured"] for item in self.history[-100:]] + [measured]
        thermal_condition = self.thermal_diagnostics.process(thermal_history)

        record = {
            "expected": expected,
            "deviations": deviations,
            "features": features,
            "anomaly": anomaly,
            "fault_classification": fault_classification,
            "sensor_fault_analysis": sensor_summary,
            "thermal_condition": thermal_condition,
            "trend": {"persistence": persistence, "direction": self.thermal_diagnostics.get_trend_direction(thermal_history)},
            "health": health,
            "severity": severity,
            "diagnosis": diagnosis,
            "rul": self._predict_rul(measured_state),
        }
        self.history.append({"timestamp": timestamp, "features": features, "deviations": deviations, "measured": measured})
        # Keep history bounded, e.g. 600 points (60s)
        if len(self.history) > 600:
            self.history.pop(0)
            
        self.last_record = record
        return record
