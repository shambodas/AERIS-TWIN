import math

from simulation.engine_simulator import EngineInputs, EngineSimulator
from intelligence.pipeline import IntelligencePipeline
from server import TwinController


def test_expectation_engine_changes_with_load():
    sim = EngineSimulator(timestep_s=0.1, random_seed=42)
    idle = EngineInputs(altitude_m=0.0, airspeed_mps=0.0, throttle_pct=20.0, mission_load_w=100.0)
    high_load = EngineInputs(altitude_m=0.0, airspeed_mps=30.0, throttle_pct=80.0, mission_load_w=300.0)

    sim.reset()
    sim.step(idle)
    baseline = sim.last_true_state
    sim.step(high_load)
    loaded = sim.last_true_state

    assert loaded.rpm >= baseline.rpm
    assert loaded.power_kw > baseline.power_kw
    assert loaded.cht_c[0] >= baseline.cht_c[0]


def test_pipeline_handles_missing_sensor_gracefully():
    pipeline = IntelligencePipeline()
    sim = EngineSimulator(timestep_s=0.1, random_seed=42)
    true_state, sensor_state = sim.step(EngineInputs(altitude_m=500.0, airspeed_mps=25.0, throttle_pct=60.0, mission_load_w=250.0))

    sensor_state.rpm = float('nan')
    output = pipeline.process(true_state, sensor_state, timestamp=sim.time_s)

    assert output["anomaly"]["is_anomaly"] in {True, False}
    assert output["health"]["score"] >= 0.0
    assert output["health"]["score"] <= 100.0
    assert output["sensor_fault_analysis"]["likely_condition"] in {"NORMAL", "POSSIBLE_SENSOR_FAULT", "POSSIBLE_ENGINE_FAULT"}
    assert output["diagnosis"]["severity"] in {"NORMAL", "INFORMATION", "WARNING", "CRITICAL", "SEVERE"}


def test_normal_classification_does_not_penalize_non_anomaly_score():
    pipeline = IntelligencePipeline()
    sim = EngineSimulator(timestep_s=0.1, random_seed=42)
    true_state, sensor_state = sim.step(
        EngineInputs(altitude_m=3500.0, airspeed_mps=30.0, throttle_pct=90.0, mission_load_w=250.0)
    )

    output = pipeline.process(true_state, sensor_state, timestamp=sim.time_s)

    assert output["fault_classification"]["fault_type"] == "NORMAL"
    assert output["anomaly"]["is_anomaly"] is False
    assert output["health"]["score"] >= 90.0


def test_pipeline_does_not_use_hidden_fault_context_for_inference():
    pipeline = IntelligencePipeline()
    sim = EngineSimulator(timestep_s=0.1, random_seed=42)

    true_state, sensor_state = sim.step(
        EngineInputs(altitude_m=3500.0, airspeed_mps=30.0, throttle_pct=60.0, mission_load_w=250.0)
    )
    without_context = pipeline.process(true_state, sensor_state, timestamp=sim.time_s)
    with_context = pipeline.process(true_state, sensor_state, timestamp=sim.time_s, fault_context="cooling_degradation")

    assert with_context["anomaly"] == without_context["anomaly"]
    assert with_context["fault_classification"] == without_context["fault_classification"]
    assert with_context["sensor_fault_analysis"] == without_context["sensor_fault_analysis"]


def test_clean_sensor_state_uses_sensor_fields_for_rul_model():
    pipeline = IntelligencePipeline()
    sim = EngineSimulator(timestep_s=0.1, random_seed=42)
    true_state, sensor_state = sim.step(
        EngineInputs(altitude_m=0.0, airspeed_mps=0.0, throttle_pct=50.0, mission_load_w=250.0)
    )

    output = pipeline.process(true_state, sensor_state, timestamp=sim.time_s)

    assert output["rul"]["available"] is True
    assert output["rul"]["status"] == "EXPERIMENTAL"
    assert output["rul"]["confidence"] is None
    assert output["rul"]["estimated_rul"] > 0.0


def test_sensor_drift_is_arbitrated_as_sensor_fault():
    pipeline = IntelligencePipeline()
    sim = EngineSimulator(timestep_s=0.1, random_seed=42)
    sim.activate_sensor_drift(drift_value=35.0, severity=0.85)
    true_state, sensor_state = sim.step(
        EngineInputs(altitude_m=0.0, airspeed_mps=0.0, throttle_pct=50.0, mission_load_w=250.0)
    )

    output = pipeline.process(true_state, sensor_state, timestamp=sim.time_s)

    assert true_state.cht_c[2] < 60.0
    assert sensor_state.cht_cylinder_3_c > true_state.cht_c[2] + 20.0
    assert output["deviations"]["cht_deviation"]["magnitude"] > 12.0
    assert output["sensor_fault_analysis"]["engine_fault_evidence"] == 0.0
    assert output["sensor_fault_analysis"]["sensor_fault_evidence"] >= 1.0
    assert output["sensor_fault_analysis"]["likely_condition"] == "POSSIBLE_SENSOR_FAULT"
    assert output["fault_classification"]["fault_type"] == "SENSOR_DRIFT"


def test_lubrication_fault_uses_observable_oil_pressure_residual():
    pipeline = IntelligencePipeline()
    sim = EngineSimulator(timestep_s=0.1, random_seed=42)
    sim.activate_lubrication_fault(0.85)
    inputs = EngineInputs(altitude_m=3500.0, airspeed_mps=30.0, throttle_pct=90.0, mission_load_w=250.0)
    for _ in range(100):
        true_state, sensor_state = sim.step(inputs)
        output = pipeline.process(true_state, sensor_state, timestamp=sim.time_s)

    assert output["deviations"]["oil_pressure_deviation"]["absolute"] < -2.0
    assert output["fault_classification"]["fault_type"] == "OIL_PRESSURE_DEGRADATION"


def test_misfire_remains_engine_fault_not_sensor_drift():
    pipeline = IntelligencePipeline()
    sim = EngineSimulator(timestep_s=0.1, random_seed=42)
    sim.activate_misfire(0.85)
    inputs = EngineInputs(altitude_m=3500.0, airspeed_mps=30.0, throttle_pct=90.0, mission_load_w=250.0)
    for _ in range(100):
        true_state, sensor_state = sim.step(inputs)
        output = pipeline.process(true_state, sensor_state, timestamp=sim.time_s)

    assert output["deviations"]["vibration_deviation"]["absolute"] > 0.25
    assert output["deviations"]["egt_deviation"]["absolute"] < -40.0
    assert output["sensor_fault_analysis"]["likely_condition"] == "POSSIBLE_ENGINE_FAULT"
    assert output["fault_classification"]["fault_type"] == "MISFIRE"


def test_reset_clears_fault_and_mission_state():
    controller = TwinController()
    controller.command({"command": "inject_fault", "parameters": {"fault": "cooling_degradation", "severity": 0.85}})
    controller.command({"command": "reset_simulation"})

    assert controller.active_fault_name == ""
    assert controller.running is False
    assert controller.flight_state == "READY"
    assert controller.mission_status == "READY"
    assert controller.mission_risk["level"] == "CLEAR"
