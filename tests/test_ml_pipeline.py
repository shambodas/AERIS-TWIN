from pathlib import Path

from intelligence.pipeline import IntelligencePipeline
from ml.model_store import ModelStore


def test_model_store_can_train_and_persist_models(tmp_path):
    dataset = Path(__file__).resolve().parents[1] / "data" / "generated" / "aeris_twin_normal.csv"
    store = ModelStore(root_dir=tmp_path)

    bundle = store.train_from_dataset(dataset)

    assert bundle["anomaly_model"] is not None
    assert bundle["fault_model"] is not None
    assert (tmp_path / "isolation_forest.pkl").exists()
    assert (tmp_path / "fault_classifier.pkl").exists()
    assert (tmp_path / "model_metadata.json").exists()

    loaded = store.load_bundle()

    assert loaded["feature_columns"]
    assert len(loaded["feature_columns"]) > 0


def test_intelligence_pipeline_uses_persisted_model_bundle(tmp_path):
    dataset = Path(__file__).resolve().parents[1] / "data" / "generated" / "aeris_twin_normal.csv"
    store = ModelStore(root_dir=tmp_path)
    store.train_from_dataset(dataset)

    pipeline = IntelligencePipeline(root_dir=tmp_path)
    assert pipeline.model_store is not None
    assert pipeline.anomaly_detector.model is not None
    assert pipeline.fault_classifier.model is not None
