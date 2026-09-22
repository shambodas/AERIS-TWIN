import sys
import os

# Ensure we can import simulation
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from simulation.engine_simulator import EngineSimulator

def test_faults():
    sim = EngineSimulator()

    faults_to_test = [
        ("MISFIRE", sim.activate_misfire),
        ("COOLING_DEGRADATION", sim.activate_cooling_fault),
        ("COMBUSTION_INSTABILITY", sim.activate_combustion_instability),
        ("EXCESSIVE_VIBRATION", sim.activate_vibration_fault),
        ("OIL_PRESSURE_DEGRADATION", sim.activate_lubrication_fault),
        ("SENSOR_DRIFT", sim.activate_sensor_drift)
    ]

    for name, method in faults_to_test:
        sim.clear_faults()
        
        # Sensor drift takes different args, others take severity
        if name == "SENSOR_DRIFT":
            method(drift_value=10.0, severity=0.8)
        else:
            method(0.8)
            
        print(f"--- Testing {name} ---")
        print(f"get_physical_fault_state(): {sim.get_physical_fault_state()}")
        print(f"get_active_fault(): {sim.get_active_fault()}\n")

if __name__ == "__main__":
    test_faults()
