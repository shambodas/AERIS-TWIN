# AERIS-TWIN Final Recovery & Acceptance Plan

This document outlines the final fixes required to pass the live acceptance test and prepare the project for the SIH demonstration. We will address the 5 specific issues raised in the prompt, ensuring no unnecessary rewrites of working code.

## User Review Required
> [!IMPORTANT]
> Please review this plan. Upon your approval, I will execute the changes and run the full `test_live_acceptance.py` suite.

## Proposed Changes

### 1. Fix Preflight / Intelligence Audit (The "Oil Pressure Degradation" bug)
During preflight (`flight_state == "READY"`), the `TwinController` forcefully overrides the health score and severity to show a clean state. However, it fails to override the underlying ML fault classification. As a result, the `intelligence["fault_classification"]["fault_type"]` and `intelligence["diagnosis"]["fault_type"]` still contain the ML's prediction (e.g., "OIL_PRESSURE_DEGRADATION" due to static ground conditions), which leaks to the UI.

#### [MODIFY] `server.py`
- In `TwinController._sample_locked`, update the preflight override block to explicitly set the fault classifications to "NORMAL".
```python
if self.flight_state == "READY" and not self.active_fault_name:
    intelligence["health"]["score"] = 100.0
    intelligence["severity"] = "NORMAL"
    intelligence["fault_classification"]["fault_type"] = "NORMAL"
    if "diagnosis" not in intelligence:
        intelligence["diagnosis"] = {}
    intelligence["diagnosis"]["fault_type"] = "NORMAL"
    intelligence["diagnosis"]["title"] = "NORMAL ENGINE OPERATION"
    intelligence["diagnosis"]["interpretation"] = "AERIS-TWIN is performing preflight checks. Sensor data is nominal."
    intelligence["diagnosis"]["recommended_action"] = "System ready for mission start."
```

### 2. Backend Authority (GCS & Dashboard)
The dashboard and GCS currently fetch state from the backend, but the GCS UI sliders (`altSlider`, `speedSlider`, `headingSlider`) do not display the actual backend state (`uav.altitude_m`, `uav.speed_mps`, `uav.heading`) for the "Current" labels, leaving them as `--`.

#### [MODIFY] `web/gcs.html`
- Update the `render()` function to populate the "Current" labels from the true `uav` state provided by the backend.
```javascript
// Inside render(s):
if (Number.isFinite(uav.altitude_m)) $('altCurrent').textContent = Math.round(uav.altitude_m) + ' m';
if (Number.isFinite(uav.speed_mps)) $('speedCurrent').textContent = Math.round(uav.speed_mps) + ' m/s';
if (Number.isFinite(uav.heading)) $('headingCurrent').textContent = String(Math.round(uav.heading)).padStart(3, '0') + '°';
```

### 3. Mission Planner UX
The layout currently allocates `0.7fr` to the map and `1.3fr` to the sidebar, making the map too small. It also contains an "EXPAND MAP" feature which violates the "single-window operation" requirement, and the layout must fit 1366x768 perfectly.

#### [MODIFY] `web/gcs.html`
- Swap the grid columns to give the map more space (e.g., `1.3fr` for map, `0.7fr` for sidebar).
- Remove the "EXPAND MAP" button and associated `toggleMap()` logic to ensure single-window operation.

### 4. Correct UAV Lifecycle
The acceptance test verifies that the server starts with `uav.status == "READY"` and `mission.running == False`. Currently, `TwinController` enforces this. No major logic changes are needed here, but the preflight fix (Issue #1) resolves the side-effects of this idle state.

## Verification Plan

### Automated Tests
I will launch the server in the background and run the full test suite:
1. `python server.py` (in background)
2. `pytest test_live_acceptance.py -v`

### Manual Verification
No manual verification is strictly required if the test suite passes, as `test_live_acceptance.py` comprehensively checks the entire lifecycle (READY -> PLAN -> START -> FLY -> FAULT -> RISK -> RTB -> RECOVER).
