import requests
import requests
import time
import re
import csv
import os

BASE = "http://localhost:8080"
RESULT_FILE = "tools/fresh_408_results.csv"

conditions = [
    ("Healthy", "NORMAL", None),
    ("cooling_degradation", "COOLING_DEGRADATION", "cooling_degradation"),
    ("low_oil_pressure", "OIL_PRESSURE_DEGRADATION", "oil_pressure_degradation"),
    ("excessive_vibration", "EXCESSIVE_VIBRATION", "excessive_vibration"),
    ("sensor_drift", "SENSOR_DRIFT", "sensor_drift"),
    ("misfire", "MISFIRE", "misfire"),
]

text = open("FINAL_REPORT.txt", encoding="utf-8").read()

routes = []
for match in re.finditer(r"Route:\s*(.+)", text):
    route = tuple(x.strip() for x in match.group(1).split("->"))
    if route not in routes:
        routes.append(route)

print("ROUTES:", len(routes))
print("CASES:", len(routes) * len(conditions))
print("SAVING TO:", RESULT_FILE)
print()

os.makedirs(os.path.dirname(RESULT_FILE), exist_ok=True)

with open(
    RESULT_FILE,
    "w",
    newline="",
    encoding="utf-8"
) as f:

    writer = csv.writer(f)

    writer.writerow([
        "Case",
        "Route",
        "Condition",
        "Expected",
        "AI_Result",
        "Confidence",
        "Result"
    ])

    f.flush()

    session = requests.Session()

    passed = 0
    failed = 0
    failures = []

    case_no = 0

    for route in routes:
        for condition, expected, fault in conditions:

            case_no += 1

            def post_command(payload):
                for attempt in range(3):
                    try:
                        res = session.post(
                            BASE + "/api/command",
                            json=payload,
                            timeout=5
                        )
                        res.raise_for_status()
                        data = res.json()
                        if not data.get("ok"):
                            raise RuntimeError(f"Command failed: {data.get('error')}")
                        return res
                    except Exception as e:
                        if attempt == 2:
                            raise RuntimeError(f"Failed to post command {payload}: {e}")
                        time.sleep(1)

            def get_state():
                for attempt in range(3):
                    try:
                        return session.get(
                            BASE + "/api/state",
                            timeout=5
                        ).json()
                    except requests.RequestException:
                        if attempt == 2:
                            raise
                        time.sleep(1)

            post_command({
                "command": "reset_simulation"
            })

            post_command({
                "command": "set_mission_route",
                "parameters": {
                    "route": list(route)
                }
            })

            if fault:
                post_command({
                    "command": "inject_fault",
                    "parameters": {
                        "fault": fault,
                        "severity": 0.85
                    }
                })

            post_command({
                "command": "start_uav"
            })

            time.sleep(2.5)

            state = get_state()

            digital = state.get("digital_twin", {})

            actual = digital.get("ai_fault")
            confidence = digital.get("ai_confidence")

            if actual == expected:
                passed += 1
                result = "PASS"
            else:
                failed += 1
                result = "FAIL"

                failures.append(
                    (
                        route,
                        condition,
                        expected,
                        actual,
                        confidence
                    )
                )

            route_text = " -> ".join(route)

            print(
                f"{case_no:03}/408 | "
                f"{route_text} | "
                f"{condition} | "
                f"AI={actual} | "
                f"{result}"
            )

            writer.writerow([
                case_no,
                route_text,
                condition,
                expected,
                actual,
                confidence,
                result
            ])

            f.flush()

print()
print("========== FINAL ==========")
print("TOTAL:", case_no)
print("PASS:", passed)
print("FAIL:", failed)
print(
    "PASS RATE:",
    round(passed / case_no * 100, 2),
    "%"
)

if failures:
    print()
    print("FIRST 10 FAILURES:")

    for failure in failures[:10]:
        print(failure)
else:
    print("ALL 408 CASES PASSED")

print()
print("RESULT FILE:", RESULT_FILE)