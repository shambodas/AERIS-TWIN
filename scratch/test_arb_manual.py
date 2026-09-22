
from intelligence.sensor_fault_arbitration import SensorFaultArbitrator

deviations = {
    'cht_deviation': {'absolute': 8.8761, 'direction': 'NEGATIVE'},
    'egt_deviation': {'absolute': 13.5019, 'direction': 'NEGATIVE'},
    'oil_temperature_deviation': {'absolute': 41.171, 'direction': 'NEGATIVE'},
    'oil_pressure_deviation': {'absolute': 0.275, 'direction': 'NEGATIVE'},
    'vibration_deviation': {'absolute': 0.8466, 'direction': 'POSITIVE'}
}

measured = {
    'cht_cylinder_1_c': 50.6,
    'oil_temperature_c': 50.0,
    'rpm': 2740.0
}

expected = {
    'expected_rpm': 2740.0
}

features = {
    'oil_temperature_deviation_rate_of_change': 0.353,
    'oil_temperature_deviation_rolling_mean': -41.74,
    'cht_deviation_rate_of_change': 0.198,
    'cht_deviation_rolling_mean': -8.40,
    'egt_deviation_rate_of_change': 0.312,
    'egt_deviation_rolling_mean': -15.72
}

arb = SensorFaultArbitrator()
print(arb.assess(measured, expected, deviations, features))

