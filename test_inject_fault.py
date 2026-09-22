import sys
import os

# Ensure we can import server
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from server import TwinController

def verify():
    # Instantiate the server (which defaults to READY, not running)
    server = TwinController()
    
    print("--- Initial State ---")
    print(f"running: {server.running}")
    print(f"telemetry status: {server.last_state['telemetry_status'] if server.last_state else 'None'}")
    
    print("\n--- Sending inject_fault command ---")
    body = {
        "command": "inject_fault",
        "parameters": {
            "fault": "excessive_vibration",
            "severity": 0.8
        }
    }
    
    # command() returns the updated state
    state = server.command(body)
    
    print("\n--- Resulting State ---")
    print(f"digital_twin.active_fault_name: {state['digital_twin']['active_fault_name']}")
    print(f"digital_twin.fault: {state['digital_twin']['fault']}")
    print(f"digital_twin.fault_severity: {state['digital_twin']['fault_severity']}")
    print(f"engine.vibration_rms: {state['engine']['vibration_rms']}")
    print(f"engine.status: {state['engine']['status']}")
    print(f"mission.running: {state['mission']['running']}")
    print(f"telemetry_status: {state['telemetry_status']}")

if __name__ == "__main__":
    verify()
