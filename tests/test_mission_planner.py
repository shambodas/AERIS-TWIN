from server import TwinController, MISSION_LOCATIONS


def test_mission_route_command_sets_route_and_waypoints():
    controller = TwinController()

    result = controller.command({
        "command": "set_mission_route",
        "parameters": {"route": ["Jaipur", "Jodhpur"]},
    })

    assert result is not None
    assert controller.mission_route == ["Jaipur", "Jodhpur"]
    assert controller.position["lat"] == MISSION_LOCATIONS["Jaipur"]["lat"]
    assert controller.position["lng"] == MISSION_LOCATIONS["Jaipur"]["lng"]
    assert controller.waypoints[0]["lat"] == MISSION_LOCATIONS["Jodhpur"]["lat"]
    assert controller.waypoints[0]["lng"] == MISSION_LOCATIONS["Jodhpur"]["lng"]


def test_mission_route_supports_four_cities():
    controller = TwinController()

    result = controller.command({
        "command": "set_mission_route",
        "parameters": {"route": ["Delhi", "Jaipur", "Jodhpur", "Ahmedabad"]},
    })

    assert result is not None
    assert controller.mission_route == ["Delhi", "Jaipur", "Jodhpur", "Ahmedabad"]
    assert len(controller.waypoints) == 3
    assert controller.waypoints[-1]["lat"] == MISSION_LOCATIONS["Ahmedabad"]["lat"]


def test_oil_pressure_fault_uses_lubrication_fault_model():
    # Setup ...
    controller = TwinController()
    
    # Inject oil_pressure_degradation via API
    controller.command({
        "command": "inject_fault", 
        "parameters": {"fault": "oil_pressure_degradation", "severity": 0.85},
    })
    controller._sample_locked()

    assert controller.simulator.lubrication_fault.is_active()
    assert controller.last_state["digital_twin"]["fault"] == "OIL_PRESSURE_DEGRADATION"


def test_return_to_base_sets_returning_route():
    controller = TwinController()
    controller.position = {"lat": 26.2389, "lng": 73.0243}
    controller.command({"command": "set_mission_route", "parameters": {"route": ["Jaipur", "Jodhpur"]}})
    controller.command({"command": "start_uav", "parameters": {"speed": 32}})

    controller.command({"command": "return_to_base"})

    assert controller.mission_status == "RETURNING"
    assert controller.mission_base == "Jaipur"
    assert controller.waypoints[0]["lat"] == MISSION_LOCATIONS["Jaipur"]["lat"]
    assert controller.waypoints[0]["lng"] == MISSION_LOCATIONS["Jaipur"]["lng"]


def test_return_to_base_resumes_from_stopped_position():
    controller = TwinController()
    controller.command({"command": "set_mission_route", "parameters": {"route": ["Delhi", "Jodhpur"]}})
    controller.command({"command": "start_uav", "parameters": {"speed": 32}})
    for _ in range(10):
        controller.tick()
    stopped_position = dict(controller.position)

    controller.command({"command": "stop_uav"})
    controller.command({"command": "return_to_base"})

    assert controller.flight_state == "FLYING"
    assert controller.running is True
    assert controller.mission_status == "RETURNING"
    assert controller.position == stopped_position
    controller.tick()
    assert controller.position != stopped_position
    assert controller.position["lat"] > stopped_position["lat"]


def test_return_to_base_is_rejected_before_flight_starts():
    controller = TwinController()
    controller.command({"command": "set_mission_route", "parameters": {"route": ["Delhi", "Jodhpur"]}})

    try:
        controller.command({"command": "return_to_base"})
    except ValueError as exc:
        assert "active or stopped flight" in str(exc)
    else:
        raise AssertionError("RTB should be rejected before flight starts")


def test_mission_risk_is_triggered_by_severe_engine_condition():
    controller = TwinController()
    controller.last_state = {
        "digital_twin": {"ai_severity": "SEVERE", "health_pct": 26.0},
        "mission": {"status": "IN_FLIGHT"},
    }

    risk = controller._mission_risk_locked()

    assert risk["level"] in {"AT_RISK", "CRITICAL"}
    assert risk["recommended_return"] is True
