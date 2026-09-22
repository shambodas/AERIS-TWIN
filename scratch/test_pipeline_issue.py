
import sys
import os
sys.path.append(os.getcwd())
from intelligence.sensor_fault_arbitration import SensorFaultArbitrator
import json

deviations = {
    'cht_deviation': {'absolute': 8.764, 'direction': 'POSITIVE'},
    'egt_deviation': {'absolute': 3.994, 'direction': 'POSITIVE'},
    'oil_temperature_deviation': {'absolute': 23.269, 'direction': 'NEGATIVE'},
    'oil_pressure_deviation': {'absolute': 0.851, 'direction': 'NEGATIVE'},
    'vibration_deviation': {'absolute': 0.845139, 'direction': 'POSITIVE'}
}

measured = {
    'cht_cylinder_1_c': 50,
    'oil_temperature_c': 50,
    'rpm': 3000
}

expected = {
    'expected_rpm': 3000
}

arbitrator = SensorFaultArbitrator()
result = arbitrator.assess(measured, expected, deviations)
print(json.dumps(result, indent=2))

