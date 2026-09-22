import time
from simulation.engine_simulator import EngineSimulator, EngineInputs

sim = EngineSimulator(timestep_s=0.1)

# Run normal for a few seconds to stabilize
inputs = EngineInputs(throttle_pct=50.0, ambient_temp_c=15.0)
for _ in range(50):
    state = sim.step(inputs)

print("--- NORMAL STATE ---")
print(f"RPM: {state.rpm:.1f}")
print(f"Total Fuel Flow: {state.fuel_flow_kg_s*3600:.3f} kg/h")
print(f"EGT Cylinder 3: {state.cylinders[2].egt_c:.1f} C")
print(f"EGT Cylinder 1: {state.cylinders[0].egt_c:.1f} C")

# Inject fault
print("\n--- INJECTING INJECTOR_ABNORMALITY (Severity 0.8) ---")
sim.activate_injector_fault(severity=0.8)

# Run for a few seconds
for _ in range(50):
    state = sim.step(inputs)

print("--- FAULT STATE ---")
print(f"RPM: {state.rpm:.1f}")
print(f"Total Fuel Flow: {state.fuel_flow_kg_s*3600:.3f} kg/h")
print(f"EGT Cylinder 3: {state.cylinders[2].egt_c:.1f} C")
print(f"EGT Cylinder 1: {state.cylinders[0].egt_c:.1f} C")
