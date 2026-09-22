import csv
import os
import re
import time
import requests

BASE = "http://localhost:8080"
RESULT_FILE = "tools/thermal_fault_results.csv"

CONDITIONS = [
    ("Healthy", "NORMAL", None),
    ("Cooling Degradation", "COOLING_DEGRADATION", "cooling"),
    ("Low Oil Pressure", "OIL_PRESSURE_DEGRADATION", "low_oil_pressure"),
    ("Excessive Vibration", "EXCESSIVE_VIBRATION", "excessive_vibration"),
    ("Sensor Drift", "SENSOR_DRIFT", "sensor_drift"),
    ("Misfire", "MISFIRE", "misfire"),
]


def get_routes():
    text = open("FINAL_REPORT.txt", encoding="utf-8").read()
    routes = []

    for match in re.finditer(r"Route:\s*(.+)", text):
        route = tuple(x.strip() for x in match.group(1).split("->"))
        if route and route not in routes:
            routes.append(route)

    return routes or [("Delhi", "Jaipur")]


def command(session, command_name, parameters=None):
    payload = {
        "command": command_name,
        "parameters": parameters or {}
    }

    response = session.post(
        BASE + "/api/command",
        json=payload,
        timeout=15
    )

    response.raise_for_status()
    return response.json()


def get_state(session):
    response = session.get(
        BASE + "/api/state",
        timeout=15
    )

    response.raise_for_status()
    return response.json()


def main():

    routes = get_routes()
    total = len(routes) * len(CONDITIONS)

    passed = 0
    failed = 0
    rows = []

    print("=" * 80)
    print("AERIS-TWIN FAULT VALIDATOR")
    print("=" * 80)
    print("Routes:", len(routes))
    print("Conditions:", len(CONDITIONS))
    print("Expected cases:", total)
    print("=" * 80)

    session = requests.Session()

    for route in routes:

        for name, expected, fault in CONDITIONS:

            case_no = len(rows) + 1

            try:

                command(
                    session,
                    "reset_simulation"
                )

                command(
                    session,
                    "set_mission_route",
                    {"route": list(route)}
                )

                if fault:

                    command(
                        session,
                        "inject_fault",
                        {
                            "fault": fault,
                            "severity": 0.85
                        }
                    )

                command(
                    session,
                    "start_uav"
                )

                time.sleep(2.5)

                data = get_state(session)

                intelligence = data.get(
                    "intelligence",
                    {}
                )

                classification = intelligence.get(
                    "fault_classification",
                    {}
                )

                actual = classification.get(
                    "fault_type",
                    "UNKNOWN"
                )

                thermal = intelligence.get(
                    "thermal_condition",
                    "UNKNOWN"
                )

                result = (
                    "PASS"
                    if actual == expected
                    else "FAIL"
                )

                if result == "PASS":
                    passed += 1
                else:
                    failed += 1

                print(
                    f"{case_no:03d} | "
                    f"{' -> '.join(route)} | "
                    f"{name} | "
                    f"ML={actual} | "
                    f"THERMAL={thermal} | "
                    f"{result}"
                )

                rows.append({
                    "case": case_no,
                    "route": " -> ".join(route),
                    "condition": name,
                    "expected_ml": expected,
                    "actual_ml": actual,
                    "thermal_condition": thermal,
                    "result": result
                })

            except Exception as exc:

                failed += 1

                print(
                    f"{case_no:03d} | "
                    f"{' -> '.join(route)} | "
                    f"{name} | "
                    f"ERROR={exc} | FAIL"
                )

                rows.append({
                    "case": case_no,
                    "route": " -> ".join(route),
                    "condition": name,
                    "expected_ml": expected,
                    "actual_ml": "ERROR",
                    "thermal_condition": "ERROR",
                    "result": "FAIL"
                })

    os.makedirs("tools", exist_ok=True)

    with open(
        RESULT_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "case",
                "route",
                "condition",
                "expected_ml",
                "actual_ml",
                "thermal_condition",
                "result"
            ]
        )

        writer.writeheader()
        writer.writerows(rows)

    rate = (
        passed / total * 100
        if total
        else 0
    )

    print()
    print("=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    print("TOTAL :", total)
    print("PASS  :", passed)
    print("FAIL  :", failed)
    print(f"RATE  : {rate:.2f}%")
    print("CSV   :", RESULT_FILE)
    print("=" * 80)


if __name__ == "__main__":
    main()