"""Train, persist, and reload the AERIS-TWIN ML models."""

from __future__ import annotations

import json
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier


class ModelStore:
    """Model persistence layer for anomaly and fault detection assets."""

    RUNTIME_FEATURES = [
        "rpm", "throttle_pct", "altitude_m", "fuel_flow_kg_s",
        "oil_temperature_c", "oil_pressure_psi", "vibration_rms",
        "cht_deviation", "egt_deviation", "oil_temperature_deviation",
        "oil_pressure_deviation", "fuel_flow_deviation", "vibration_deviation",
        "alternator_power_deviation", "injection_timing_deviation_deg",
    ]

    def __init__(self, root_dir: str | Path | None = None):
        base_dir = Path(root_dir) if root_dir is not None else Path(__file__).resolve().parent / "model_artifacts"
        self.root_dir = Path(base_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

        self.anomaly_path = self.root_dir / "isolation_forest.pkl"
        self.fault_path = self.root_dir / "fault_classifier.pkl"
        self.metadata_path = self.root_dir / "model_metadata.json"

    def _prepare_training_matrix(self, dataset_path: str | Path):
        from intelligence.deviations import compute_deviations
        from intelligence.features import FeatureEngineer
        from intelligence.physics_expectation import PhysicsExpectationEngine

        df = pd.read_csv(dataset_path)
        if df.empty:
            raise ValueError(f"Dataset is empty: {dataset_path}")

        numeric_df = df.select_dtypes(include=[np.number]).copy()
        if "fault_label" in df.columns:
            label_series = pd.to_numeric(df["fault_label"], errors="coerce")
            numeric_df["fault_label"] = label_series
        else:
            label_series = None

        if "fault_type" in df.columns:
            numeric_df = numeric_df.drop(columns=["fault_type"], errors="ignore")

        feature_columns = self.RUNTIME_FEATURES
        column_map = {
            "rpm": "measured_rpm", "throttle_pct": "true_throttle_pct",
            "altitude_m": "true_altitude_m", "fuel_flow_kg_s": "measured_fuel_flow_kg_s",
            "oil_temperature_c": "measured_oil_temperature_c", "oil_pressure_psi": "measured_oil_pressure_psi",
            "vibration_rms": "measured_vibration_rms",
        }
        expectation = PhysicsExpectationEngine()
        feature_engineer = FeatureEngineer()
        rows = []
        for _, row in numeric_df.iterrows():
            measured = {
                "rpm": row.get("measured_rpm", 0.0),
                "throttle_pct": row.get("true_throttle_pct", 50.0),
                "altitude_m": row.get("true_altitude_m", 0.0),
                "ambient_temperature_c": row.get("true_ambient_temperature_c", 15.0),
                "pressure_kpa": row.get("true_manifold_pressure_kpa", 101.0),
                "air_density_kg_m3": row.get("true_air_density_kg_m3", 1.225),
                "power_kw": row.get("measured_power_kw", 0.0),
                "torque_nm": row.get("measured_torque_nm", 0.0),
                "cht": row.get("measured_cht_cylinder_3_c", 0.0),
                "egt": row.get("measured_egt_cylinder_3_c", 0.0),
                "oil_temperature_c": row.get("measured_oil_temperature_c", 0.0),
                "oil_temperature": row.get("measured_oil_temperature_c", 0.0),
                "oil_pressure_psi": row.get("measured_oil_pressure_psi", 0.0),
                "oil_pressure": row.get("measured_oil_pressure_psi", 0.0),
                "fuel_flow_kg_s": row.get("measured_fuel_flow_kg_s", 0.0),
                "fuel_flow": row.get("measured_fuel_flow_kg_s", 0.0),
                "vibration_rms": row.get("measured_vibration_rms", 0.0),
                "vibration": row.get("measured_vibration_rms", 0.0),
                "alternator_power_w": row.get("measured_alternator_power_w", 0.0),
                "injection_timing_deviation_deg": row.get("measured_injection_timing_deviation_deg", 0.0),
            }
            expected = expectation.calculate(operating_state=measured, measured_state=measured)
            deviations = compute_deviations(expected, measured)
            features = feature_engineer.build(expected, measured, deviations)
            rows.append([features.get(feature, 0.0) for feature in feature_columns])
        feature_matrix = pd.DataFrame(rows, columns=feature_columns, index=numeric_df.index)
        if not feature_columns:
            raise ValueError(f"No usable numeric feature columns found in dataset: {dataset_path}")

        feature_matrix = feature_matrix.replace([np.inf, -np.inf], np.nan).dropna()
        if feature_matrix.empty:
            raise ValueError(f"No valid rows after filtering NaN/inf in dataset: {dataset_path}")

        if label_series is not None:
            labels = df.loc[feature_matrix.index, "fault_type"].fillna("NORMAL") if "fault_type" in df.columns else label_series.loc[feature_matrix.index].fillna(0).map({0: "NORMAL", 1: "MISFIRE", 2: "COOLING_DEGRADATION", 3: "COMBUSTION_INSTABILITY", 4: "SENSOR_DRIFT", 5: "OIL_PRESSURE_DEGRADATION", 6: "EXCESSIVE_VIBRATION", 7: "INJECTOR_ABNORMALITY"})
            return feature_matrix, labels, feature_columns
        return feature_matrix, None, feature_columns

    def train_from_dataset(self, dataset_path: str | Path) -> dict[str, Any]:
        dataset_path = Path(dataset_path)
        X, y, feature_columns = self._prepare_training_matrix(dataset_path)

        anomaly_model = IsolationForest(
            n_estimators=300,
            contamination="auto",
            random_state=42,
            n_jobs=-1,
        )
        anomaly_model.fit(X)

        if y is None:
            raise ValueError("Dataset does not contain a fault label column required for supervised fault training.")

        fault_model = RandomForestClassifier(
            n_estimators=300,
            max_depth=None,
            random_state=42,
            class_weight="balanced_subsample",
        )
        fault_model.fit(X, y)

        self._save_model(self.anomaly_path, anomaly_model)
        self._save_model(self.fault_path, fault_model)

        metadata = {
            "dataset": str(dataset_path),
            "trained_at_utc": datetime.now(timezone.utc).isoformat(),
            "feature_columns": feature_columns,
            "label_values": sorted(str(v) for v in np.unique(y)),
            "anomaly_model": self.anomaly_path.name,
            "fault_model": self.fault_path.name,
        }
        self.metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        return {
            "anomaly_model": anomaly_model,
            "fault_model": fault_model,
            "feature_columns": feature_columns,
            "metadata": metadata,
        }

    def load_bundle(self) -> dict[str, Any]:
        if not self.anomaly_path.exists() or not self.fault_path.exists():
            raise FileNotFoundError(f"No persisted model bundle found in {self.root_dir}")

        metadata = json.loads(self.metadata_path.read_text(encoding="utf-8")) if self.metadata_path.exists() else {}
        anomaly_model = self._load_model(self.anomaly_path)
        fault_model = self._load_model(self.fault_path)

        return {
            "anomaly_model": anomaly_model,
            "fault_model": fault_model,
            "feature_columns": metadata.get("feature_columns", []),
            "metadata": metadata,
        }

    @staticmethod
    def _save_model(path: Path, model: Any) -> None:
        with path.open("wb") as handle:
            pickle.dump(model, handle)

    @staticmethod
    def _load_model(path: Path) -> Any:
        with path.open("rb") as handle:
            return pickle.load(handle)


def train_default_models() -> dict[str, Any]:
    dataset_dir = Path(__file__).resolve().parents[1] / "data" / "generated"
    candidate_files = [f for f in sorted(dataset_dir.glob("*.csv")) if f.name != "_combined_training_dataset.csv"]
    if not candidate_files:
        raise FileNotFoundError(f"No generated datasets found in {dataset_dir}")
    if len(candidate_files) > 1:
        combined = pd.concat((pd.read_csv(path) for path in candidate_files), ignore_index=True)
        dataset_path = dataset_dir / "_combined_training_dataset.csv"
        combined.to_csv(dataset_path, index=False)
    else:
        dataset_path = candidate_files[0]
    store = ModelStore()
    return store.train_from_dataset(dataset_path)
