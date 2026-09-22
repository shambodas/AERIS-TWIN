import subprocess, sys, time, urllib.request, json

p = subprocess.Popen([sys.executable, 'server.py'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(3)

def cmd(payload, timeout=30):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        'http://localhost:8080/api/command', data=data,
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def get():
    with urllib.request.urlopen("http://localhost:8080/api/state", timeout=5) as r:
        return json.loads(r.read())

try:
    print("reset...")
    cmd({"command": "reset_simulation"})
    cmd({"command": "set_mission_route", "parameters": {"route": ["Delhi", "Jaipur"]}})
    cmd({"command": "start_uav"})
    print("fast_forward 120s...")
    t0 = time.perf_counter()
    cmd({"command": "fast_forward", "parameters": {"seconds": 120.0}})
    elapsed = time.perf_counter() - t0
    print(f"fast_forward took {elapsed:.2f}s real time")
    s = get()
    dt = s.get("digital_twin", {})
    print(f"time_s={dt.get('simulation_time_s')}, ai_fault={dt.get('ai_fault')}")
    print("inject cooling_degradation...")
    cmd({"command": "inject_fault", "parameters": {"fault": "cooling_degradation", "severity": 0.85}})
    time.sleep(2.5)
    s = get()
    dt = s.get("digital_twin", {})
    print(f"COOLING test: time_s={dt.get('simulation_time_s')}, ai={dt.get('ai_fault')}, conf={dt.get('ai_confidence')}")
    print()
    print("--- NORMAL case ---")
    cmd({"command": "reset_simulation"})
    cmd({"command": "set_mission_route", "parameters": {"route": ["Delhi", "Jaipur"]}})
    cmd({"command": "start_uav"})
    cmd({"command": "fast_forward", "parameters": {"seconds": 120.0}})
    time.sleep(2.5)
    s = get()
    dt = s.get("digital_twin", {})
    print(f"NORMAL test: time_s={dt.get('simulation_time_s')}, ai={dt.get('ai_fault')}, conf={dt.get('ai_confidence')}")
except Exception as e:
    import traceback; traceback.print_exc()
finally:
    p.kill()
    print("Server stopped.")
