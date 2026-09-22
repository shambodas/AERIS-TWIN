# AERIS-TWIN FAULT VOCABULARY AUDIT

## 1. CANONICAL FAULT TABLE

| Condition | API Name | Physical/Simulator Name | ML Label | Dataset | UI Label | Diagnostic Type | ML Trained | Physical | UI |
|---|---|---|---|---|---|---|---|---|---|
| **Normal** | N/A | `NORMAL` | `NORMAL` | `NORMAL` | N/A | `NORMAL` | Yes | Yes | No |
| **Cooling Degradation** | `cooling_degradation` | `COOLING_DEGRADATION` | `COOLING_DEGRADATION` (meta) / `OVERHEATING` (fallback) | `COOLING_DEGRADATION` | Cooling Degradation | `COOLING_DEGRADATION` | Yes | Yes | Yes |
| **Oil Pressure Degradation** | `low_oil_pressure` | `OIL_PRESSURE_DEGRADATION` | `OIL_PRESSURE_DEGRADATION` | `OIL_PRESSURE_DEGRADATION` | Oil Pressure | `OIL_PRESSURE_DEGRADATION` | Yes | Yes | Yes |
| **Excessive Vibration** | `excessive_vibration` | `EXCESSIVE_VIBRATION` | `EXCESSIVE_VIBRATION` | `EXCESSIVE_VIBRATION` | Vibration | `EXCESSIVE_VIBRATION` | Yes | Yes | Yes |
| **Combustion Instability**| `combustion_instability`| `COMBUSTION_INSTABILITY` | `COMBUSTION_INSTABILITY` | `COMBUSTION_INSTABILITY` | Combustion Instability | `COMBUSTION_INSTABILITY`| Yes | Yes | Yes |
| **Misfire** | `misfire` | `MISFIRE` | `MISFIRE` | `MISFIRE` | Misfire | `MISFIRE` | Yes | Yes | Yes |
| **Sensor Drift** | `sensor_drift` | `SENSOR_DRIFT` | `SENSOR_DRIFT` | `SENSOR_DRIFT` | Sensor Drift | `SENSOR_DRIFT` | Yes | Yes | Yes |
| **Injector Abnormality** | `injector_abnormality` | `INJECTOR_ABNORMALITY` | `INJECTOR_ABNORMALITY` (fallback only) | *Not found* | Injector Abnormality | `INJECTOR_ABNORMALITY`| **No** | Yes | Yes |
| **Engine Failure** | N/A | `ENGINE_FAILURE` | N/A | N/A | N/A | N/A | No | Yes | No |


## 2. ALL FAULT/CONDITION NAMES FOUND

### Current Canonical
- `NORMAL`
- `COOLING_DEGRADATION`
- `OIL_PRESSURE_DEGRADATION`
- `EXCESSIVE_VIBRATION`
- `COMBUSTION_INSTABILITY`
- `MISFIRE`
- `SENSOR_DRIFT`
- `INJECTOR_ABNORMALITY`
- `ENGINE_FAILURE` (Physical engine RUL 0 state)
- `POSSIBLE_SENSOR_FAULT` (Internal sensor analytics state)

### Compatibility Aliases
- `cooling` (Internal API mapping for `cooling_degradation`)
- `lubrication` (Internal API mapping for `low_oil_pressure`)
- `low_oil_pressure` (API injection name for Oil Pressure Degradation)
- `oil_pressure` (Legacy API mapping key -> `lubrication`)

### Legacy/Obsolete (Present in codebase but unsupported or mismatched)
- `overheating` (Used in `test_e2e.py` and `test_intelligence_pipeline.py` for API injection, but fails in `server.py`)
- `OVERHEATING` (Used in ML fallback classifier map for class 2, despite dataset being `COOLING_DEGRADATION`)
- `FUEL_FLOW_ABNORMALITY` (ML Fallback `classes` list)
- `SENSOR_BIAS` (ML Fallback `classes` list)
- `SENSOR_DROPOUT` (ML Fallback `classes` list)
- `ABNORMAL_TEMPERATURE_RESPONSE` (ML Fallback `classes` list and heuristic)


## 3. CURRENT ML CLASSES

Derived from `ml/model_artifacts/model_metadata.json` (actual trained artifact):
- `COMBUSTION_INSTABILITY`
- `COOLING_DEGRADATION`
- `EXCESSIVE_VIBRATION`
- `MISFIRE`
- `NORMAL`
- `OIL_PRESSURE_DEGRADATION`
- `SENSOR_DRIFT`

*Note: `intelligence/fault_classifier.py` defines a larger list of 12 classes (`OVERHEATING`, `FUEL_FLOW_ABNORMALITY`, `INJECTOR_ABNORMALITY`, etc.) which mismatch the actual trained model outputs.*


## 4. DATASET CLASSES

Found matching the ML metadata list above:
- `COMBUSTION_INSTABILITY`
- `COOLING_DEGRADATION`
- `EXCESSIVE_VIBRATION`
- `MISFIRE`
- `NORMAL`
- `OIL_PRESSURE_DEGRADATION`
- `SENSOR_DRIFT`


## 5. UI → API → PHYSICS → ML MAPPING

UI "Cooling Degradation"
→ API `cooling_degradation` (mapped to `cooling` internally)
→ Simulator `COOLING_DEGRADATION`
→ ML `COOLING_DEGRADATION` (Trained meta) / `OVERHEATING` (Fallback)

UI "Oil Pressure"
→ API `low_oil_pressure` (mapped to `lubrication` internally)
→ Simulator `OIL_PRESSURE_DEGRADATION`
→ ML `OIL_PRESSURE_DEGRADATION`

UI "Vibration"
→ API `excessive_vibration`
→ Simulator `EXCESSIVE_VIBRATION`
→ ML `EXCESSIVE_VIBRATION`

UI "Combustion Instability"
→ API `combustion_instability`
→ Simulator `COMBUSTION_INSTABILITY`
→ ML `COMBUSTION_INSTABILITY`

UI "Sensor Drift"
→ API `sensor_drift`
→ Simulator `SENSOR_DRIFT`
→ ML `SENSOR_DRIFT`

UI "Misfire"
→ API `misfire`
→ Simulator `MISFIRE`
→ ML `MISFIRE`

UI "Injector Abnormality"
→ API `injector_abnormality`
→ Simulator `INJECTOR_ABNORMALITY`
→ ML *(Not Trained)* -> `INJECTOR_ABNORMALITY` (Fallback Int 7)


## 6. INCONSISTENCIES

- **E2E Test Injection Bug**: `test_e2e.py` and `test_intelligence_pipeline.py` attempt to inject a fault via API with `{"fault": "overheating"}`. However, `overheating` is missing from the `FAULT_NAMES` map in `server.py` line 55. This will result in an `Unsupported fault` ValueError.
- **Cooling vs Overheating**: The simulator and ML metadata output `COOLING_DEGRADATION` (label 2). However, `intelligence/fault_classifier.py` maps integer 2 to `OVERHEATING` and uses `OVERHEATING` as a fallback class, creating a split vocabulary for the same condition.
- **Injector Abnormality is not trained**: The fault is implemented in the UI, API, Simulator, and Diagnostics, but `INJECTOR_ABNORMALITY` is missing from the trained dataset labels in `model_metadata.json`. If the actual ML model predicts, it will never output this class.
- **Redundant Alias Chain**: To inject oil pressure degradation, the UI sends `low_oil_pressure`, which `server.py` maps to `lubrication`, which triggers a method that sets the internal state to `OIL_PRESSURE_DEGRADATION`.
- **Obsolete Classifier Classes**: `intelligence/fault_classifier.py` contains 12 `self.classes` (e.g. `SENSOR_BIAS`, `FUEL_FLOW_ABNORMALITY`), 5 of which are completely obsolete and unused by the current dataset or simulator.


## 7. RECOMMENDATION

Establish a single 1:1 mapping standard where the API, Simulator, ML Label, and Diagnostic Type use the exact same string (UPPERCASE for internal state, lowercase for API). 

Proposed Standard Canonical Vocabulary:
1. `NORMAL`
2. `COOLING_DEGRADATION`
3. `OIL_PRESSURE_DEGRADATION`
4. `EXCESSIVE_VIBRATION`
5. `COMBUSTION_INSTABILITY`
6. `MISFIRE`
7. `SENSOR_DRIFT`
8. `INJECTOR_ABNORMALITY`

*Remove `cooling` and `lubrication` internal routing aliases. Remove `OVERHEATING` entirely. Remove obsolete classes from `fault_classifier.py`. Fix tests to inject `cooling_degradation` instead of `overheating`.*


## 8. FILES INSPECTED

- `server.py`
- `web/index.html`
- `web/gcs.html`
- `simulation/engine_simulator.py`
- `intelligence/fault_classifier.py`
- `intelligence/diagnostics.py`
- `intelligence/pipeline.py`
- `intelligence/health_score.py`
- `ml/model_artifacts/model_metadata.json`
- `test_e2e.py`
- `tests/test_intelligence_pipeline.py`
- `tests/test_rul_foundation.py`
- `ui_audit_checkpoint.json`
