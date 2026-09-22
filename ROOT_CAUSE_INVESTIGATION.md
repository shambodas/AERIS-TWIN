# Root Cause Investigation: AERIS-TWIN Intelligence Bugs

This report details the root-cause analysis for the two bugs observed during the live `EXCESSIVE_VIBRATION` validation test. 

As requested, this was a read-only investigation. **No code has been modified.**

---

## BUG 1: `EXCESSIVE_VIBRATION` misclassified as `SENSOR_DRIFT`

**Symptom:**
During an `EXCESSIVE_VIBRATION` injection, the physical vibration deviation was successfully detected (`engine_fault_evidence = 0.8`), but `sensor_fault_evidence` spiked to `1.5`, causing the `SensorFaultArbitrator` to declare a `POSSIBLE_SENSOR_FAULT`. The classifier subsequently output `SENSOR_DRIFT`.

**Root Cause:**
1. **Steady-State Expectations vs. Thermal Inertia:** In September 2026, `intelligence/physics_expectation.py` was recalibrated to remove the `time_s` variable, converting it to a purely steady-state model based on RPM and throttle. However, the physical engine simulation still models thermal inertia (e.g., a cold engine takes time to warm up).
2. **Transient Negative Deviations:** Because expected temperatures jump instantly with throttle while actual temperatures rise slowly, the difference (`actual - expected`) produces large negative deviations during early flight or throttle spikes (e.g., `cht_deviation = -49.7°C`, `oil_temperature_deviation = -79.8°C`).
3. **Signed Deviation Fix Exposes Flaw:** The previous intelligence layer bug dropped signs, making all deviations absolute/positive. Now that the recent fixes properly propagate negative signs, these transient negative values reach the `SensorFaultArbitrator`.
4. **Hardcoded Sensor Heuristics:** In `intelligence/sensor_fault_arbitration.py`, there is a block of code designed to catch physically impossible scenarios:
   ```python
   # Unphysical directions (engines overheat, they don't magically freeze)
   if cht_dev < -30.0:
       sensor_evidence += 1.5
   if oil_temp_dev < -40.0:
       sensor_evidence += 1.5
   ```
   Because of the thermal inertia transient, these conditions evaluate to `True`. The arbitrator misinterprets normal engine warm-up as a "plummeting" sensor fault, injecting exactly `1.5` into `sensor_fault_evidence` and overriding the `0.8` vibration evidence.

---

## BUG 2: Massive Vibration (+7.04) fails Anomaly Threshold

**Symptom:**
A normalized vibration deviation of `+7.04` (raw `+0.845`) generated an anomaly score of only `0.4639`, failing to cross the `0.55` threshold.

**Root Cause:**
1. **Isolation Forest Blind Spot:** The ML model (`IsolationForestAnomalyDetector`) was trained on datasets where `features.py` historically passed absolute, sign-stripped deviations. Feeding it signed data combined with massive negative thermal transients causes the Isolation Forest to output a decision function score that maps to `0.4639`, failing to recognize the severe vibration as an anomaly.
2. **Bypassed Deterministic Safety Nets:** The `IsolationForestAnomalyDetector.score()` method in `intelligence/anomaly_detector.py` contains robust fallback heuristics and deterministic limits designed to catch precisely this scenario:
   ```python
   score = min(1.0, max(0.0, sum(normalized) / len(normalized)))
   # ...
   if abs(features.get("vibration_deviation", 0.0)) > 0.30:
       score = max(score, 0.5)
   ```
   If executed, these fallbacks would have produced a score of `1.0`.
3. **The Logical Flaw:** The method currently fast-fails and returns the `model_score` *immediately*, entirely bypassing the deterministic limits:
   ```python
   def score(self, features: dict) -> float:
       model_score = self._score_from_model(features)
       if model_score is not None:
           return model_score  # <--- Bypass occurs here
       
       # Fallback heuristics and limits are never reached if model loads successfully
   ```
   Because the ML model successfully loads in production, the safety limits are never applied to the ML output.

---

## Proposed Remediation (Pending Approval)

1. **Bug 1 (Arbitrator):**
   * Adjust the `SensorFaultArbitrator` heuristics to only flag "unphysical directions" if the engine is sufficiently warmed up (e.g., `actual_temperature > 50°C`) or if the deviation drop is extremely sudden relative to the immediate history, rather than just negative relative to a steady-state expectation.

2. **Bug 2 (Anomaly Detector):**
   * Move the deterministic boundary checks (`max(score, 0.5)`) to execute *after* `model_score` is calculated, ensuring that catastrophic deviations always clip the final score upward, regardless of whether the score came from the ML model or the fallback heuristics. 
   * Alternatively, blend the fallback normalized score with the ML model score to ensure robustness against out-of-distribution sign changes.
