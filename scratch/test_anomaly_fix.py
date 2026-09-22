
from intelligence.anomaly_detector import IsolationForestAnomalyDetector

# 1. Test model presence but overriding with safety guard
class MockModel:
    def decision_function(self, df):
        return [0.0]  # Score ~ 0.5 (below 0.55 threshold)

detector = IsolationForestAnomalyDetector(model=MockModel())

features = {
    'vibration_rms': 0.993,          # Should trigger > 0.6 guard
    'vibration_deviation': 0.845,    # Should also trigger > 0.30 guard
    'cht_deviation': 5.0
}

# Apply my fix exactly
def _apply_deterministic_guards(self, features: dict, base_score: float) -> float:
    safety_score = base_score
    if abs(features.get('cht_deviation', 0.0)) > 24.0 or abs(features.get('egt_deviation', 0.0)) > 36.0:
        safety_score = max(safety_score, 0.4)
    if abs(features.get('vibration_deviation', 0.0)) > 0.30 or float(features.get('vibration_rms', 0.0)) > 0.6:
        safety_score = max(safety_score, 0.60)
    return safety_score

def score(self, features: dict) -> float:
    model_score = self._score_from_model(features)
    if model_score is None:
        base_score = 0.0 # simplified fallback for mock
    else:
        base_score = model_score
    safety_score = self._apply_deterministic_guards(features, base_score)
    return float(min(1.0, max(0.0, safety_score)))

def detect(self, features: dict) -> dict:
    final_score = self.score(features)
    return {
        'score': final_score,
        'is_anomaly': final_score > 0.55,
        'normalized_score': final_score,
        'threshold': 0.55,
    }

IsolationForestAnomalyDetector._apply_deterministic_guards = _apply_deterministic_guards
IsolationForestAnomalyDetector.score = score
IsolationForestAnomalyDetector.detect = detect

res = detector.detect(features)
print(res)

