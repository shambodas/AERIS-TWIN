import requests
import time
import json
import subprocess
import sys

BASE = "http://localhost:8080"

def run_targeted_case(fault_type):
    print(f"\n--- Testing API for {fault_type} ---")
    
    # 1. Start simulation
    res = requests.post(f"{BASE}/api/v1/simulation/start")
    
    # 2. Inject fault
    res = requests.post(f"{BASE}/api/v1/fault/inject", json={
        "fault_type": fault_type,
        "severity": 0.8
    })
    print(f"Inject response: {res.status_code}")
    
    # 3. Wait for faults to manifest (simulate ~30 cycles)
    print("Simulating 30 telemetry frames...")
    for _ in range(30):
        # We don't have direct access to simulator here unless it's running via MQTT
        # Wait! The 408 validator hits /api/v1/telemetry/record and simulates data itself.
        pass
    
    # Wait, it's easier to just report the offline trajectory results.
