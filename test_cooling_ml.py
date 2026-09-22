from simulation.engine_simulator import EngineInputs
from simulation.engine_simulator import EngineSimulator
from intelligence.pipeline import IntelligencePipeline

sim = EngineSimulator()
intel = IntelligencePipeline()

inputs = EngineInputs(altitude_m=1000.0, airspeed_mps=30.0, throttle_pct=70.0)

for _ in range(30):
    sim.step(inputs)

print("Normal:")
result = intel.process(sim.last_true_state, sim.last_sensor_state, sim.time_s)
print(result["fault_classification"]["fault_type"])

sim.activate_cooling_fault(0.85)

for _ in range(30):
    sim.step(inputs)

print("Cooling fault:")
result = intel.process(sim.last_true_state, sim.last_sensor_state, sim.time_s)
print(result["fault_classification"]["fault_type"])
