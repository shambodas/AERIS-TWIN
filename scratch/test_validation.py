
from intelligence.sensor_fault_arbitration import SensorFaultArbitrator

arb = SensorFaultArbitrator()

def test_healthy_cold_startup():
    measured = {'cht_cylinder_1_c': 30.0, 'cht_cylinder_2_c': 30.0, 'cht_cylinder_3_c': 30.0, 'cht_cylinder_4_c': 30.0, 'oil_temperature_c': 20.0, 'rpm': 2500.0}
    expected = {'expected_rpm': 2500.0}
    deviations = {
        'cht_deviation': {'absolute': 40.0, 'direction': 'NEGATIVE'},
        'egt_deviation': {'absolute': 50.0, 'direction': 'NEGATIVE'},
        'oil_temperature_deviation': {'absolute': 50.0, 'direction': 'NEGATIVE'}
    }
    features = {
        'cht_deviation_rate_of_change': 0.5,
        'cht_deviation_rolling_mean': -41.0,
        'egt_deviation_rate_of_change': 0.6,
        'egt_deviation_rolling_mean': -51.0,
        'oil_temperature_deviation_rate_of_change': 0.8,
        'oil_temperature_deviation_rolling_mean': -51.0
    }
    result = arb.assess(measured, expected, deviations, features)
    print('Healthy Cold Startup:', result['sensor_fault_evidence'] == 0.0, result)

test_healthy_cold_startup()

