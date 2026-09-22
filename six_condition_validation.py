import json
import time
import urllib.request
from datetime import datetime

BASE = "http://localhost:8080"

API_STATE = f"{BASE}/api/state"
API_COMMAND = f"{BASE}/api/command"
API_EVENTS = f"{BASE}/api/events"
API_FLIGHTS = f"{BASE}/api/flights"

CONDITIONS = [
    "Healthy",
    "cooling_degradation",
    "low_oil_pressure",
    "excessive_vibration",
    "sensor_drift",
    "misfire",
]

ROUTE = ["Delhi", "Jaipur"]

EXPECTED = {
    "Healthy": "NORMAL",
    "cooling_degradation": "COOLING_DEGRADATION",
    "low_oil_pressure": "OIL_PRESSURE_DEGRADATION",
    "excessive_vibration": "EXCESSIVE_VIBRATION",
    "sensor_drift": "SENSOR_DRIFT",
    "misfire": "MISFIRE",
}


def get_json(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        return {"_error": str(e)}


def post_json(url, payload):
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")

            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"_raw": body}

    except Exception as e:
        return {"_error": str(e)}


def get_events():
    result = get_json(API_EVENTS)

    if isinstance(result, list):
        return result

    if isinstance(result, dict):
        events = result.get("events", [])
        if isinstance(events, list):
            return events

    return []


def wait_for_state(target, timeout=60):
    deadline = time.time() + timeout

    while time.time() < deadline:
        state = get_json(API_STATE)

        telemetry = state.get("telemetry", {})
        current = telemetry.get("state")

        if current == target:
            return True

        time.sleep(1)

    return False


def extract_state():
    state = get_json(API_STATE)

    telemetry = state.get("telemetry", {})
    intelligence = state.get("intelligence", {})

    classification = intelligence.get("fault_classification", {})

    if isinstance(classification, dict):
        fault_type = classification.get("fault_type", "Unknown")
    else:
        fault_type = str(classification)

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),

        "simulation_state": telemetry.get("state"),
        "simulation_time": telemetry.get("time_s"),

        "oil_pressure": telemetry.get("oil_pressure_psi"),
        "oil_temperature": telemetry.get("oil_temperature_c"),

        "cht": telemetry.get("cht_cylinder_1_c"),
        "egt": telemetry.get("egt_cylinder_1_c"),

        "vibration": telemetry.get("vibration_rms"),

        "wear_index": (
            telemetry.get("wear_index")
            if telemetry.get("wear_index") is not None
            else state.get("wear_index")
        ),

        "active_fault": (
            state.get("fault", {}).get("type")
            if isinstance(state.get("fault"), dict)
            else state.get("fault")
        ),

        "classification": fault_type,
        "confidence": intelligence.get("confidence"),
        "severity": intelligence.get("severity"),
        "mission_risk": intelligence.get("mission_risk"),
    }


def find_flight_closed(events, flight_id=None):
    matches = []

    for event in events:
        if not isinstance(event, dict):
            continue

        message = str(event.get("message", ""))
        kind = str(event.get("kind", ""))

        if "FLIGHT CLOSED" not in message.upper():
            continue

        if flight_id:
            if flight_id in message:
                matches.append(event)
        else:
            matches.append(event)

    return matches


def extract_flight_id(state):
    possible = [
        state.get("flight_id"),
        state.get("session_id"),
        state.get("flight", {}).get("id")
        if isinstance(state.get("flight"), dict)
        else None,
    ]

    for value in possible:
        if value:
            return value

    return None


def run_condition(condition):
    print("\n" + "=" * 80)
    print(f"TESTING: {condition}")
    print("=" * 80)

    # Ensure UAV is stopped before starting the new session.
    post_json(API_COMMAND, {"command": "stop_uav"})
    time.sleep(2)

    # Clear any previous fault.
    post_json(API_COMMAND, {"command": "clear_fault"})
    time.sleep(1)

    # Set route.
    route_result = post_json(
        API_COMMAND,
        {
            "command": "set_route",
            "route": ROUTE,
        },
    )

    time.sleep(1)

    # Capture events BEFORE this flight.
    events_before = get_events()

    # Start new flight.
    start_result = post_json(
        API_COMMAND,
        {
            "command": "start_uav",
        },
    )

    time.sleep(2)

    # IMPORTANT:
    # Capture the clean starting state BEFORE fault injection.
    starting_state = extract_state()

    flight_id = extract_flight_id(get_json(API_STATE))

    print("Starting state:")
    print(json.dumps(starting_state, indent=2))

    # Inject selected fault AFTER clean baseline is captured.
    injection_result = None

    if condition != "Healthy":
        injection_result = post_json(
            API_COMMAND,
            {
                "command": "inject_fault",
                "fault": condition,
            },
        )

        time.sleep(2)

    state_after_injection = get_json(API_STATE)

    simulator_fault = "Unknown"

    fault_data = state_after_injection.get("fault")

    if isinstance(fault_data, dict):
        simulator_fault = (
            fault_data.get("type")
            or fault_data.get("name")
            or "Unknown"
        )
    elif fault_data:
        simulator_fault = str(fault_data)

    # Wait until flight begins.
    flying = wait_for_state("FLYING", timeout=30)

    # Allow intelligence layer to process telemetry.
    time.sleep(10)

    mid_state = extract_state()

    # Wait for mission completion.
    reached_idle = wait_for_state("IDLE", timeout=90)

    time.sleep(2)

    ending_state = extract_state()

    events_after = get_events()

    # Search COMPLETE event list.
    closed_matches = find_flight_closed(
        events_after,
        flight_id
    )

    if not closed_matches:
        # If flight ID is unavailable, search globally.
        closed_matches = find_flight_closed(events_after)

    flight_closed = len(closed_matches) > 0

    flights = get_json(API_FLIGHTS)

    classification = mid_state.get("classification", "Unknown")
    expected = EXPECTED[condition]

    classification_pass = classification == expected

    print("\nEnding state:")
    print(json.dumps(ending_state, indent=2))

    print("\nFLIGHT CLOSED events:")
    print(json.dumps(closed_matches, indent=2))

    print("\nClassification:", classification)
    print("Expected:", expected)
    print("Classification PASS:", classification_pass)
    print("Mission reached IDLE:", reached_idle)
    print("FLIGHT CLOSED:", flight_closed)

    return {
        "condition": condition,

        "route": ROUTE,

        "flight_id": flight_id,

        "route_command": route_result,
        "start_command": start_result,
        "injection_command": injection_result,

        "simulator_fault": simulator_fault,

        "starting_state": starting_state,
        "state_after_injection": state_after_injection,
        "mid_flight_state": mid_state,
        "ending_state": ending_state,

        "expected_classification": expected,
        "actual_classification": classification,
        "classification_pass": classification_pass,

        "mission_reached_idle": reached_idle,

        "flight_closed": flight_closed,
        "flight_closed_events": closed_matches,

        "flights_api_response": flights,
    }


def main():
    print("=" * 80)
    print("AERIS-TWIN CONTROLLED SIX-CONDITION VALIDATION")
    print("=" * 80)

    print("\nThis script modifies NO production files.")
    print("Route:", " -> ".join(ROUTE))
    print("Conditions:", ", ".join(CONDITIONS))

    # Check server before beginning.
    initial = get_json(API_STATE)

    if "_error" in initial:
        print("\nERROR: AERIS-TWIN server is not reachable.")
        print(initial["_error"])
        print("\nStart the server first with:")
        print("python server.py")
        return

    print("\nServer is reachable.")

    results = []

    for condition in CONDITIONS:
        try:
            result = run_condition(condition)
            results.append(result)
        except Exception as e:
            print(f"\nERROR while testing {condition}: {e}")

            results.append({
                "condition": condition,
                "error": str(e),
            })

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    print("\n\n" + "=" * 110)
    print("SUMMARY")
    print("=" * 110)

    header = (
        f"{'Condition':<22}"
        f"{'Start Oil':<12}"
        f"{'End Oil':<12}"
        f"{'Start Wear':<13}"
        f"{'End Wear':<13}"
        f"{'AI Classification':<28}"
        f"{'Expected':<28}"
        f"{'PASS':<7}"
        f"{'CLOSED':<8}"
    )

    print(header)
    print("-" * 143)

    for result in results:

        if "error" in result:
            print(
                f"{result['condition']:<22}"
                f"ERROR: {result['error']}"
            )
            continue

        start = result["starting_state"]
        end = result["ending_state"]

        start_oil = start.get("oil_pressure")
        end_oil = end.get("oil_pressure")

        start_wear = start.get("wear_index")
        end_wear = end.get("wear_index")

        classification = result.get(
            "actual_classification",
            "Unknown"
        )

        expected = result.get(
            "expected_classification",
            "Unknown"
        )

        passed = result.get(
            "classification_pass",
            False
        )

        closed = result.get(
            "flight_closed",
            False
        )

        print(
            f"{result['condition']:<22}"
            f"{str(start_oil):<12}"
            f"{str(end_oil):<12}"
            f"{str(start_wear):<13}"
            f"{str(end_wear):<13}"
            f"{classification:<28}"
            f"{expected:<28}"
            f"{str(passed):<7}"
            f"{str(closed):<8}"
        )

    # ------------------------------------------------------------------
    # Save detailed JSON + readable report
    # ------------------------------------------------------------------

    report = {
        "generated_at": datetime.now().isoformat(),
        "route": ROUTE,
        "conditions": CONDITIONS,
        "results": results,
    }

    with open(
        "controlled_validation_report_v2.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(report, f, indent=2, default=str)

    with open(
        "controlled_validation_report_v2.txt",
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            "AERIS-TWIN CONTROLLED SIX-CONDITION VALIDATION\n"
        )
        f.write("=" * 80 + "\n\n")

        f.write(
            f"Generated: {report['generated_at']}\n"
        )
        f.write(
            f"Route: {' -> '.join(ROUTE)}\n"
        )

        f.write("\n\nSUMMARY\n")
        f.write("=" * 80 + "\n")

        f.write(header + "\n")
        f.write("-" * 143 + "\n")

        for result in results:

            if "error" in result:
                f.write(
                    f"{result['condition']}: "
                    f"ERROR: {result['error']}\n"
                )
                continue

            start = result["starting_state"]
            end = result["ending_state"]

            f.write(
                f"{result['condition']:<22}"
                f"{str(start.get('oil_pressure')):<12}"
                f"{str(end.get('oil_pressure')):<12}"
                f"{str(start.get('wear_index')):<13}"
                f"{str(end.get('wear_index')):<13}"
                f"{result.get('actual_classification', 'Unknown'):<28}"
                f"{result.get('expected_classification', 'Unknown'):<28}"
                f"{str(result.get('classification_pass', False)):<7}"
                f"{str(result.get('flight_closed', False)):<8}\n"
            )

        f.write("\n\nDETAILED RESULTS\n")
        f.write("=" * 80 + "\n\n")

        for result in results:
            f.write(
                json.dumps(
                    result,
                    indent=2,
                    default=str
                )
            )
            f.write("\n\n")

    print("\n")
    print("=" * 80)
    print("VALIDATION COMPLETE")
    print("=" * 80)
    print("\nGenerated:")
    print("  controlled_validation_report_v2.txt")
    print("  controlled_validation_report_v2.json")


if __name__ == "__main__":
    main()