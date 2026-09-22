import time
import requests

BASE_URL = "http://localhost:8080"

def log(msg):
    print(f"[*] {msg}")

def test_api():
    # 1. Reset
    log("Resetting simulation...")
    requests.post(f"{BASE_URL}/api/simulation/reset", json={})
    time.sleep(1)

    # 2. Plan Mission
    log("Planning mission...")
    res = requests.post(f"{BASE_URL}/api/command", json={"command": "set_mission_route", "parameters": {"route": ["Delhi", "Jaipur", "Jodhpur"]}}).json()
    assert res["state"]["mission"]["route"] == ["Delhi", "Jaipur", "Jodhpur"]
    
    # 3. Start Mission
    log("Starting mission...")
    requests.post(f"{BASE_URL}/api/command", json={"command": "start_mission", "parameters": {"route": ["Delhi", "Jaipur", "Jodhpur"]}})
    time.sleep(4)  # Let it fly a bit
    
    # 4. Check Telemetry & Movement
    state = requests.get(f"{BASE_URL}/api/state").json()
    log(f"UAV Position: {state['uav']['position']}")
    log(f"Engine Health: {state['digital_twin']['health_pct']}")
    log(f"Engine Status: {state['engine']['status']}")
    
    assert state["engine"]["status"] == "HEALTHY", (
        f"Normal flight became unhealthy: status={state['engine']['status']}, "
        f"severity={state['intelligence'].get('severity')}, "
        f"health={state['intelligence'].get('health', {}).get('score')}"
    )
    assert state["intelligence"]["severity"] in {"NORMAL", "INFORMATION"}
    assert state["digital_twin"]["health_pct"] > 0.0
    assert state["digital_twin"]["ai_fault"] == "NORMAL"

    # 5. RUL check
    rul = state["intelligence"].get("rul", {})
    log(f"RUL Available: {rul.get('available')}, Status: {rul.get('status')}")

    # 6. Inject Fault (Cooling Degradation)
    log("Injecting Cooling Degradation Fault...")
    requests.post(f"{BASE_URL}/api/command", json={"command": "inject_fault", "parameters": {"fault": "cooling_degradation", "severity": 0.8}})
    time.sleep(3) # Wait for thermal effects

    state = requests.get(f"{BASE_URL}/api/state").json()
    log(f"Engine Status After Fault: {state['engine']['status']}")
    log(f"Mission Risk: {state['mission']['risk_level']}")
    log(f"Deviation: {state['intelligence']['deviations'].get('cht_deviation', {}).get('absolute')}")
    log(f"Diagnosis: {state['intelligence']['diagnosis'].get('interpretation')}")

    # 7. Return to Base
    log("Triggering Return to Base...")
    requests.post(f"{BASE_URL}/api/command", json={"command": "return_to_base", "parameters": {}})
    time.sleep(2)
    state = requests.get(f"{BASE_URL}/api/state").json()
    log(f"Return Target Waypoint: {state['flight_path']['waypoints'][0]}")

    # 8. Test Sensor Drift
    log("Clearing Faults...")
    requests.post(f"{BASE_URL}/api/command", json={"command": "clear_fault", "parameters": {}})
    time.sleep(2)

    log("Injecting Sensor Drift...")
    requests.post(f"{BASE_URL}/api/command", json={"command": "inject_fault", "parameters": {"fault": "sensor_drift", "severity": 0.8}})
    time.sleep(2)
    state = requests.get(f"{BASE_URL}/api/state").json()
    sfa = state["intelligence"].get("sensor_fault_analysis", {})
    log(f"Sensor Fault Analysis: {sfa.get('likely_condition')}")

    log("End to end test completed successfully.")

if __name__ == "__main__":
    test_api()
