import time
import requests

def run_backend_smoke():
    print("Testing server...")
    requests.post("http://localhost:8080/api/simulation/reset")
    
    # Set waypoints
    r = requests.post("http://localhost:8080/api/command", json={
        "command": "set_waypoints",
        "parameters": {
            "waypoints": [
                {"lat": 28.6139, "lng": 77.2090}, # Delhi
                {"lat": 26.9124, "lng": 75.7873}, # Jaipur
                {"lat": 26.2389, "lng": 73.0243}  # Jodhpur
            ]
        }
    })
    print("set_waypoints:", r.json()["state"]["flight_path"])
    
    # Start UAV
    r = requests.post("http://localhost:8080/api/command", json={
        "command": "start_uav",
        "parameters": {
            "altitude": 3500,
            "speed": 32,
            "heading": 45
        }
    })
    print("start_uav:", r.json()["state"]["uav"]["position"])
    
    for _ in range(5):
        time.sleep(0.5)
        r = requests.get("http://localhost:8080/api/state")
        state = r.json()
        print("pos:", state["uav"]["position"], "speed:", state["uav"]["speed_mps"])

if __name__ == "__main__":
    run_backend_smoke()
