"""Standalone RTB diagnostic; intentionally not auto-collected by pytest."""
import time

import requests


BASE_URL = "http://localhost:8080"
DELHI = {"lat": 28.6139, "lng": 77.2090}


def api(command, params=None):
    response = requests.post(
        f"{BASE_URL}/api/command",
        json={"command": command, "parameters": params or {}},
        timeout=5,
    )
    return response.json()


def state():
    return requests.get(f"{BASE_URL}/api/state", timeout=5).json()


def run_rtb_test():
    print("=== RESET ===")
    api("reset_simulation")
    time.sleep(0.3)

    print("\n=== SELECT ROUTE: Delhi -> Mumbai -> Jodhpur ===")
    result = api("set_mission_route", {"route": ["Delhi", "Mumbai", "Jodhpur"]})
    selected = result.get("state", {})
    print(f"  mission_base (derived): {selected.get('mission', {}).get('base')}")
    print(f"  route: {selected.get('mission', {}).get('route')}")
    print(f"  UAV start pos: {selected.get('uav', {}).get('position')}")
    print(f"  following: {selected.get('flight_path', {}).get('following')}")

    print("\n=== START UAV, let it fly for 5s ===")
    api("start_uav", {"altitude": 3500, "speed": 50, "heading": 270})
    time.sleep(5)
    selected = state()
    mid_pos = selected["uav"]["position"]
    print(f"  Position after 5s flight: lat={mid_pos['lat']:.5f} lng={mid_pos['lng']:.5f}")
    print(f"  Route remaining: {selected['mission']['route']}")
    print(f"  Status: {selected['uav']['status']}")
    distance = ((mid_pos["lat"] - DELHI["lat"]) ** 2 + (mid_pos["lng"] - DELHI["lng"]) ** 2) ** 0.5
    print(f"  Distance from Delhi: ~{distance:.3f} degrees (should be >0)")

    print("\n=== RETURN TO BASE ===")
    selected = api("return_to_base").get("state", {})
    print(f"  mission_status: {selected.get('mission', {}).get('status')}")
    print(f"  waypoints: {selected.get('flight_path', {}).get('waypoints')}")
    print(f"  route_waypoints: {selected.get('flight_path', {}).get('route')}")
    print(f"  following: {selected.get('flight_path', {}).get('following')}")
    print(f"  flight_state: {selected.get('uav', {}).get('status')}")

    print("\n=== POLLING DURING RTB ===")
    previous_distance = distance
    reached = False
    for index in range(30):
        time.sleep(1)
        selected = state()
        position = selected["uav"]["position"]
        distance = ((position["lat"] - DELHI["lat"]) ** 2 + (position["lng"] - DELHI["lng"]) ** 2) ** 0.5
        approaching = distance < previous_distance
        status = selected["uav"]["status"]
        mission_status = selected["mission"]["status"]
        print(f"  t+{index + 1}s: lat={position['lat']:.5f} lng={position['lng']:.5f} | dist_from_base={distance:.4f} | approaching={approaching} | status={status}/{mission_status}")
        previous_distance = distance
        if mission_status in ("RECOVERED", "COMPLETED", "READY") and status == "READY":
            print(f"  --> RTB COMPLETE at t+{index + 1}s")
            reached = True
            break

    print("\n=== FINAL POSITION ===")
    selected = state()
    position = selected["uav"]["position"]
    final_distance = ((position["lat"] - DELHI["lat"]) ** 2 + (position["lng"] - DELHI["lng"]) ** 2) ** 0.5
    print(f"  Final: lat={position['lat']:.6f} lng={position['lng']:.6f}")
    print(f"  Delhi: lat={DELHI['lat']:.6f} lng={DELHI['lng']:.6f}")
    print(f"  Final dist from Delhi: {final_distance:.6f} degrees")
    print(f"  RTB reached base: {reached}")
    print(f"  Status: {selected['uav']['status']} / {selected['mission']['status']}")


if __name__ == "__main__":
    run_rtb_test()
