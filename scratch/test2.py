
from intelligence.anomaly_detector import IsolationForestAnomalyDetector
from ml.model_store import ModelStore
store = ModelStore()
bundle = store.load_bundle()
model = bundle['anomaly_model']
detector = IsolationForestAnomalyDetector(model=model, root_dir='ml/model_artifacts')
features = {
    'rpm': 3000.0,
    'throttle_pct': 50.0,
    'altitude_m': 0.0,
    'fuel_flow_kg_s': 0.00005,
    'oil_temperature_c': 15.0,
    'oil_pressure_psi': 60.0,
    'vibration_rms': 0.993,
    'cht_deviation': -49.7,
    'egt_deviation': -59.6,
    'oil_temperature_deviation': -79.8,
    'oil_pressure_deviation': -26.2,
    'fuel_flow_deviation': 0.0,
    'vibration_deviation': 0.845139
}
print('Final combined score:', detector.score(features))

