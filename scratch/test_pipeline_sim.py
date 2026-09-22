
import sys
import os
sys.path.append(os.getcwd())
from physical_engine.engine_simulator import EngineSimulator
from physical_engine.fault_model import inject_fault, PhysicalFault
from physical_engine.regimes import get_flight_regime, get_environmental_conditions
from intelligence.pipeline import IntelligencePipeline
import json
import logging
logging.basicConfig(level=logging.INFO)

simulator = EngineSimulator()
inject_fault(simulator, PhysicalFault.EXCESSIVE_VIBRATION, severity=0.8)

env = get_environmental_conditions('CRUISE')
inputs = get_flight_regime('CRUISE')
for _ in range(300):
    simulator.step(1.0, inputs, env)

pipeline = IntelligencePipeline()
measured, expected = simulator.get_sensors(), simulator.get_expected_sensors()
result = pipeline.process(measured, expected)

print('\nPIPELINE RESULT:')
print(json.dumps(result, indent=2))

