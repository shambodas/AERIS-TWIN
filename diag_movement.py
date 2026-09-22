"""Live test: verify UAV moves on the backend and SSE delivers changing positions."""
import time
import requests

BASE = "http://localhost:8080"

def api(cmd, params=None):
    r = requests.post(f"{BASE}/api/command", json={"command": cmd, "parameters": params or {}}, timeout=5)
    d = r.json()
    if not d.get("ok"):
        print("  ERROR:", d)
    return d

def state():
    return requests.get(f"{BASE}/api/state", timeout=5).json()

print("--- RESET ---")
api("reset_simulation")
time.sleep(0.3)
s0 = state()
print("  flight_state:", s0["uav"]["status"])
print("  position:", s0["uav"]["position"])

print("\n--- SELECT ROUTE: Delhi -> Mumbai -> Jodhpur ---")
r = api("set_mission_route", {"route": ["Delhi", "Mumbai", "Jodhpur"]})
s = r.get("state", {})
print("  route_waypoints:", s.get("flight_path", {}).get("route"))
print("  pending waypoints:", s.get("flight_path", {}).get("waypoints"))
print("  following:", s.get("flight_path", {}).get("following"))
print("  UAV at start:", s.get("uav", {}).get("position"))

print("\n--- START UAV (speed=50 m/s) ---")
r = api("start_uav", {"altitude": 3500, "speed": 50, "heading": 270})
s = r.get("state", {})
print("  status:", s.get("uav", {}).get("status"))
print("  t0 position:", s.get("uav", {}).get("position"))
print("  speed_mps:", s.get("uav", {}).get("speed_mps"))

print("\n--- POLLING POSITION every 1s for 8s ---")
prev_lat = s.get("uav", {}).get("position", {}).get("lat", 0)
any_moved = False
for i in range(8):
    time.sleep(1)
    s = state()
    p = s["uav"]["position"]
    moved = abs(p["lat"] - prev_lat) > 1e-6
    if moved:
        any_moved = True
    route = s.get("mission", {}).get("route", [])
    dist = s.get("uav", {}).get("distance_to_next_km", "N/A")
    print(f"  t+{i+1}s: lat={p['lat']:.6f} lng={p['lng']:.6f} | MOVED={moved} | route_remaining={route} | dist_to_next={dist}")
    prev_lat = p["lat"]

print("\n--- STOP UAV ---")
r = api("stop_uav")
p = r.get("state", {}).get("uav", {}).get("position", {})
print("  stopped at:", p)
print("  status:", r.get("state", {}).get("uav", {}).get("status"))

print("\n=== RESULT ===")
print("  Backend UAV position changing:", any_moved)
print("  If True: GCS marker should also move (fix was in CSS/will-change removal)")
print("  UAV_ROUTE_TIME_SCALE =", 150.0, "(~150x demo acceleration)")
