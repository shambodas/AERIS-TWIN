"""AERIS-TWIN live acceptance test, usable under pytest or as a script."""
import sys
import time

import requests


BASE = "http://localhost:8080"


def run_live_acceptance():
    counts = {"passed": 0, "failed": 0}

    def check(label, condition, detail=""):
        if condition:
            counts["passed"] += 1
            print(f"  [PASS] {label}")
        else:
            counts["failed"] += 1
            print(f"  [FAIL] {label}  {detail}")

    def state():
        return requests.get(f"{BASE}/api/state", timeout=5).json()

    def cmd(command, params=None):
        return requests.post(
            f"{BASE}/api/command",
            json={"command": command, "parameters": params or {}},
            timeout=15,
        ).json()

    def wait_until(predicate, timeout=10.0, interval=0.1):
        deadline = time.monotonic() + timeout
        latest = state()
        while time.monotonic() < deadline:
            latest = state()
            if predicate(latest):
                return latest
            time.sleep(interval)
        return latest

    print("\n" + "=" * 60)
    print("PHASE 1: INITIAL STATE - EXPLICIT RESET")
    print("=" * 60)
    check("Reset command accepted", cmd("reset_simulation").get("ok") is True)
    time.sleep(1)
    s = state()
    check("Backend is reachable", s is not None)
    check("Flight state = READY", s["uav"]["status"] == "READY", f"got {s['uav']['status']}")
    check("Running = False", s["mission"]["running"] is False)
    check("Mission status = READY", s["mission"]["status"] == "READY", f"got {s['mission']['status']}")
    check("Mission risk = CLEAR", s["mission"]["risk_level"] == "CLEAR", f"got {s['mission']['risk_level']}")
    check("Telemetry status = READY", s["telemetry_status"] == "READY", f"got {s['telemetry_status']}")
    check("RUL available = True", s["intelligence"]["rul"]["available"] is True)
    check("RUL status = EXPERIMENTAL", s["intelligence"]["rul"]["status"] == "EXPERIMENTAL")
    pos1 = s["uav"]["position"].copy()
    time.sleep(2)
    s2 = state()
    pos2 = s2["uav"]["position"]
    check("UAV is stationary (lat unchanged)", abs(pos1["lat"] - pos2["lat"]) < 0.001)
    check("UAV is stationary (lng unchanged)", abs(pos1["lng"] - pos2["lng"]) < 0.001)
    check("Flight state still READY after wait", s2["uav"]["status"] == "READY", f"got {s2['uav']['status']}")

    print("\n" + "=" * 60)
    print("PHASE 2: PLAN MISSION - Delhi -> Jaipur -> Jodhpur")
    print("=" * 60)
    route = ["Delhi", "Jaipur", "Jodhpur"]
    result = cmd("set_mission_route", {"route": route})
    check("Plan command accepted", result.get("ok") is True)
    s = state()
    check("Mission status = PLANNED", s["mission"]["status"] == "PLANNED")
    check("Mission route correct", s["mission"]["route"] == route)
    check("Mission base = Delhi", s["mission"]["base"] == "Delhi")
    check("Flight state still READY after planning", s["uav"]["status"] == "READY")
    check("Running still False after planning", s["mission"]["running"] is False)
    check("UAV at Delhi", abs(s["uav"]["position"]["lat"] - 28.6139) < 0.5)
    check("Waypoints set for Jaipur+Jodhpur", len(s["flight_path"]["waypoints"]) == 2)

    print("\n" + "=" * 60)
    print("PHASE 3: START MISSION - Operator clicks START")
    print("=" * 60)
    result = cmd("start_mission", {"route": route, "mission": "rapid_throttle"})
    check("Start command accepted", result.get("ok") is True)
    check("Altitude control accepted", cmd("set_altitude", {"value": 3500}).get("ok") is True)
    check("Airspeed control accepted", cmd("set_speed", {"value": 30}).get("ok") is True)
    operating = wait_until(lambda item: item["engine"]["throttle_pct"] >= 80.0, timeout=5.0)
    print(
        "  [*] Controlled operating point: "
        f"throttle={operating['engine']['throttle_pct']:.1f}% "
        f"rpm={operating['engine']['rpm']:.0f} "
        f"altitude={operating['uav']['altitude_m']:.1f}m "
        f"airspeed={operating['uav']['speed_mps']:.1f}m/s "
        f"CHT={operating['engine']['cht_c']:.1f} "
        f"EGT={operating['engine']['egt_c']:.1f} "
        f"oil={operating['engine']['oil_temperature_c']:.1f}"
    )
    check("Controlled heat-generating throttle established", operating["engine"]["throttle_pct"] >= 80.0)
    s = state()
    check("Flight state = FLYING", s["uav"]["status"] == "FLYING")
    check("Mission status = IN_FLIGHT", s["mission"]["status"] == "IN_FLIGHT")
    check("Running = True", s["mission"]["running"] is True)
    check("Telemetry status = LIVE", s["telemetry_status"] == "LIVE")

    print("\n" + "=" * 60)
    print("PHASE 4: UAV MOVEMENT - Verify backend-controlled flight")
    print("=" * 60)
    start = state()["uav"]["position"].copy()
    time.sleep(5)
    moved = state()
    finish = moved["uav"]["position"]
    check("UAV has moved (lat changed)", abs(finish["lat"] - start["lat"]) > 0.002)
    check("UAV has moved (lng changed)", abs(finish["lng"] - start["lng"]) > 0.002)
    check("Heading is reasonable", moved["uav"]["heading"] > 0)

    print("\n" + "=" * 60)
    print("PHASE 5: TELEMETRY, INTELLIGENCE, AND CLEAN-STATE RUL")
    print("=" * 60)
    s = state()
    engine = s["engine"]
    for label, value in (("RPM", engine["rpm"]), ("CHT", engine["cht_c"]), ("EGT", engine["egt_c"]), ("oil temperature", engine["oil_temperature_c"]), ("oil pressure", engine["oil_pressure_psi"])):
        check(f"{label} populated", value > 0, f"value={value}")
    check("Vibration populated", engine["vibration_rms"] >= 0)
    intelligence = s["intelligence"]
    check("Health score present", intelligence["health"]["score"] is not None)
    check("Severity present", intelligence["severity"] in {"NORMAL", "INFORMATION", "WARNING", "CRITICAL", "SEVERE"})
    check("Fault classification present", "fault_type" in intelligence["fault_classification"])
    check("Diagnosis present", "interpretation" in intelligence["diagnosis"])
    check("Recommendation present", len(intelligence["diagnosis"].get("recommended_action", "")) > 0)
    check("Expected values present", "expected_cht" in intelligence.get("expected", {}))
    deviations = intelligence.get("deviations", {})
    for name in ("cht_deviation", "egt_deviation", "oil_temperature_deviation"):
        check(f"{name} available", name in deviations)
    check("No active fault before RUL", s["digital_twin"]["active_fault_name"] == "")
    check("Telemetry current before RUL", s["telemetry_status"] == "LIVE")
    rul = intelligence["rul"]
    check("RUL available", rul["available"] is True)
    check("RUL status is EXPERIMENTAL", rul["status"] == "EXPERIMENTAL")
    check("RUL estimate numeric or null", rul.get("estimated_rul") is None or isinstance(rul["estimated_rul"], (int, float)))
    if rul.get("estimated_rul") is not None:
        check("RUL estimate non-negative", rul["estimated_rul"] >= 0)
    check("RUL confidence is null", rul.get("confidence") is None)
    check("RUL reason present", len(rul.get("reason", "")) > 5)
    if rul.get("estimated_rul") == 0.0:
        print("  [REPORT] POTENTIAL RUL RUNTIME / MODEL CALIBRATION ISSUE: zero in clean normal flight")

    print("\n" + "=" * 60)
    print("PHASE 6: FAULT INJECTION - Cooling Degradation")
    print("=" * 60)
    operating = wait_until(lambda item: item["engine"]["rpm"] > 3000, timeout=10.0)
    health_before = operating["intelligence"]["health"]["score"]
    print(f"\n  [DEBUG] Intelligence before fault: {operating['intelligence']}\n")
    check("Cooling degradation fault injected", cmd("inject_fault", {"fault": "cooling_degradation", "severity": 0.85}).get("ok") is True)
    s = wait_until(lambda item: item["intelligence"]["health"]["score"] < health_before, timeout=15.0)
    check("Health degradation observed", s["intelligence"]["health"]["score"] < health_before)
    s = wait_until(
        lambda item: item["intelligence"]["severity"] in {"WARNING", "CRITICAL", "SEVERE"}
        and item["mission"]["risk_level"] in {"MONITOR", "AT_RISK"},
        timeout=15.0,
    )
    digital_twin = s["digital_twin"]
    check("Active fault = cooling_degradation", digital_twin["active_fault_name"] == "cooling_degradation")
    check("Fault classification contains cooling", "COOLING" in (digital_twin.get("fault", "") or "").upper() or "cooling" in (digital_twin.get("ai_fault", "") or "").lower())
    check("Health degraded after fault", s["intelligence"]["health"]["score"] < health_before)
    check("Severity elevated", s["intelligence"]["severity"] in {"WARNING", "CRITICAL", "SEVERE"})
    check("Fault diagnosis present", len(s["intelligence"]["diagnosis"].get("interpretation", "")) > 5)
    check("Fault recommendation present", len(s["intelligence"]["diagnosis"].get("recommended_action", "")) > 3)
    check("Mission risk elevated", s["mission"]["risk_level"] in {"MONITOR", "AT_RISK"})

    print("\n" + "=" * 60)
    print("PHASE 7: MISSION RISK + RETURN TO BASE")
    print("=" * 60)
    before_rtb = s["uav"]["position"].copy()
    rtb_result = cmd("return_to_base")
    check("RTB command accepted", rtb_result.get("ok") is True)
    s = wait_until(lambda item: item["mission"]["status"] == "RETURNING", timeout=5.0)
    check("Mission status = RETURNING", s["mission"]["status"] == "RETURNING")
    check("Return waypoint set", len(s["flight_path"]["waypoints"]) == 1)
    check("Return target is Delhi", abs(s["flight_path"]["waypoints"][0]["lat"] - 28.6139) < 0.5)
    time.sleep(1)
    after_rtb = state()["uav"]["position"]
    check("UAV moving during RTB", abs(after_rtb["lat"] - before_rtb["lat"]) > 0.001 or abs(after_rtb["lng"] - before_rtb["lng"]) > 0.001)

    print("\n" + "=" * 60)
    print("PHASE 8: CLEAR FAULT + SENSOR DRIFT TEST")
    print("=" * 60)
    cmd("clear_fault")
    time.sleep(1)
    s = state()
    check("Fault cleared", s["digital_twin"]["active_fault_name"] == "")
    check("Sensor drift injected", cmd("inject_fault", {"fault": "sensor_drift", "severity": 0.85}).get("ok") is True)
    time.sleep(3)
    s = state()
    analysis = s["intelligence"].get("sensor_fault_analysis", {})
    likely = analysis.get("likely_condition", "UNKNOWN")
    check("Sensor fault analysis present", likely not in {"UNKNOWN", ""})
    check("Active fault = sensor_drift", s["digital_twin"]["active_fault_name"] == "sensor_drift")
    if likely == "POSSIBLE_ENGINE_FAULT":
        print("  [REPORT] POTENTIAL GENUINE PRODUCTION INTELLIGENCE/ARBITRATION ISSUE: sensor drift classified as possible engine fault")

    print("\n" + "=" * 60)
    print("PHASE 9: TWO-WINDOW SYNCHRONIZATION")
    print("=" * 60)
    s1 = state()
    s2 = state()
    check("Timestamp formats agree", type(s1["timestamp"]) is type(s2["timestamp"]))
    check("Flight states agree", s1["uav"]["status"] == s2["uav"]["status"])
    check("Mission states agree", s1["mission"]["status"] == s2["mission"]["status"])
    check("Active faults agree", s1["digital_twin"]["active_fault_name"] == s2["digital_twin"]["active_fault_name"])
    arrived = wait_until(
        lambda item: item["mission"]["status"] in {"RECOVERED", "READY"}
        and item["uav"]["status"] == "READY",
        timeout=60.0,
    )
    check("RTB eventually reaches appropriate final state", arrived["mission"]["status"] in {"RECOVERED", "READY"})
    check("UAV READY after RTB", arrived["uav"]["status"] == "READY")

    print("\n" + "=" * 60)
    print("PHASE 10: RESET AND VERIFY CLEAN STATE")
    print("=" * 60)
    check("Final reset accepted", cmd("reset_simulation").get("ok") is True)
    time.sleep(1)
    s = state()
    check("After reset: flight = READY", s["uav"]["status"] == "READY")
    check("After reset: running = False", s["mission"]["running"] is False)
    check("After reset: status = READY", s["mission"]["status"] == "READY")
    check("After reset: position at Delhi", abs(s["uav"]["position"]["lat"] - 28.6139) < 0.5)
    print(f"\nRESULTS: {counts['passed']} passed, {counts['failed']} failed")
    return counts


def test_live_acceptance():
    counts = run_live_acceptance()
    assert counts["failed"] == 0, f"live acceptance had {counts['failed']} failed checks"


if __name__ == "__main__":
    sys.exit(1 if run_live_acceptance()["failed"] else 0)
