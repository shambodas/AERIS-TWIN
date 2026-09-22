import os

from server import TwinController


def test_flight_session_starts_and_closes_once():
    controller = TwinController()

    controller.command({"command": "start_uav", "parameters": {"altitude": 3500, "speed": 50, "heading": 270}})

    assert controller.current_flight_id is not None
    assert controller.flight_active is True
    assert controller.flight_start_time is not None
    assert controller.flight_statistics["telemetry_points"] >= 0

    controller.command({"command": "stop_uav"})

    assert controller.flight_active is False
    assert controller.current_flight_id is None


def test_flight_session_is_not_reused_for_ready_state():
    controller = TwinController()

    assert controller.current_flight_id is None
    assert controller.flight_active is False

    controller.command({"command": "reset_simulation"})

    assert controller.current_flight_id is None
    assert controller.flight_active is False
    assert controller.flight_state == "READY"
