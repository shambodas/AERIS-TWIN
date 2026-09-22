
from intelligence.sensor_fault_arbitration import SensorFaultArbitrator
import json

deviations = {
    'cht_deviation': {'absolute': 8.0, 'direction': 'NEGATIVE'},
    'egt_deviation': {'absolute': 15.6, 'direction': 'NEGATIVE'},
    'oil_temperature_deviation': {'absolute': 41.67, 'direction': 'NEGATIVE'},
    'oil_pressure_deviation': {'absolute': 0.68, 'direction': 'POSITIVE'},
    'vibration_deviation': {'absolute': 0.85, 'direction': 'POSITIVE'}
}

measured = {
    'cht_cylinder_1_c': 51.5,
    'oil_temperature_c': 49.6,
    'rpm': 2803
}

expected = {
    'expected_rpm': 2803
}

features = {
    'oil_temperature_deviation_rate_of_change': 1.21,
    'oil_temperature_deviation_rolling_mean': -41.77,
    'cht_deviation_rate_of_change': -0.34,
    'cht_deviation_rolling_mean': -8.59,
    'egt_deviation_rate_of_change': 1.06,
    'egt_deviation_rolling_mean': -15.75
}

arbitrator = SensorFaultArbitrator()
# We will modify the arbitrator in memory to test the logic
def assess_fixed(self, measured, expected, deviations, features=None):
    def get_signed(dev_dict):
        val = abs(float(dev_dict.get('absolute', 0.0)))
        return -val if dev_dict.get('direction') == 'NEGATIVE' else val

    cht_dev = get_signed(deviations.get('cht_deviation', {}))
    egt_dev = get_signed(deviations.get('egt_deviation', {}))
    oil_temp_dev = get_signed(deviations.get('oil_temperature_deviation', {}))
    oil_pressure_dev = get_signed(deviations.get('oil_pressure_deviation', {}))
    vibration_dev = abs(float(deviations.get('vibration_deviation', {}).get('absolute', 0.0)))

    cht_channels = [float(measured.get(f'cht_cylinder_{i}_c', 0.0)) for i in range(1, 5)]
    isolated_cht_outlier = max(cht_channels) - min(cht_channels) > 12.0
    
    engine_evidence = 0.0
    sensor_evidence = 0.0

    if isolated_cht_outlier and vibration_dev < 0.15:
        sensor_evidence += 1.0
        
    if not isolated_cht_outlier and abs(cht_dev) > 12.0 and abs(egt_dev) < 5.0 and abs(oil_temp_dev) < 5.0 and abs(oil_pressure_dev) < 3.0 and vibration_dev < 0.12:
        sensor_evidence += 1.0
        
    engine_is_warm = max(cht_channels) > 50.0 or float(measured.get('oil_temperature_c', 0.0)) > 50.0
    
    cht_roc = float(features.get('cht_deviation_rate_of_change', 0.0)) if features else 0.0
    egt_roc = float(features.get('egt_deviation_rate_of_change', 0.0)) if features else 0.0
    oil_temp_roc = float(features.get('oil_temperature_deviation_rate_of_change', 0.0)) if features else 0.0
    
    cht_rolling = float(features.get('cht_deviation_rolling_mean', cht_dev)) if features else cht_dev
    egt_rolling = float(features.get('egt_deviation_rolling_mean', egt_dev)) if features else egt_dev
    oil_rolling = float(features.get('oil_temperature_deviation_rolling_mean', oil_temp_dev)) if features else oil_temp_dev

    def is_implausible_drop(dev, roc, rolling, threshold, is_warm):
        if dev >= threshold:
            return False
        has_history = abs(roc) > 1e-5 or abs(rolling - dev) > 1e-5
        if has_history:
            if roc < -5.0: return True
            if rolling > (threshold * 0.5): return True
            return False
        return is_warm

    if is_implausible_drop(cht_dev, cht_roc, cht_rolling, -30.0, engine_is_warm):
        sensor_evidence += 1.5
    if is_implausible_drop(egt_dev, egt_roc, egt_rolling, -40.0, engine_is_warm):
        sensor_evidence += 1.5
    if is_implausible_drop(oil_temp_dev, oil_temp_roc, oil_rolling, -40.0, engine_is_warm):
        sensor_evidence += 1.5
    if oil_pressure_dev > 30.0:
        sensor_evidence += 1.5

    if not isolated_cht_outlier and cht_dev > 10.0 and egt_dev > 10.0 and oil_temp_dev > 8.0:
        engine_evidence += 1.0
    if oil_pressure_dev < -8.0 and abs(float(measured.get('rpm', 0.0)) - float(expected.get('expected_rpm', 0.0))) < 200.0:
        engine_evidence += 0.7
    if vibration_dev > 0.15 and abs(float(measured.get('rpm', 0.0)) - float(expected.get('expected_rpm', 0.0))) < 250.0:
        engine_evidence += 0.8

    if sensor_evidence > engine_evidence: likely = 'POSSIBLE_SENSOR_FAULT'
    elif engine_evidence > sensor_evidence: likely = 'POSSIBLE_ENGINE_FAULT'
    else: likely = 'AMBIGUOUS'

    return {
        'engine_fault_evidence': round(engine_evidence, 3),
        'sensor_fault_evidence': round(sensor_evidence, 3),
        'ambiguous_evidence': max(0.0, abs(engine_evidence - sensor_evidence)),
        'likely_condition': likely
    }

SensorFaultArbitrator.assess = assess_fixed
result = arbitrator.assess(measured, expected, deviations, features)
print(json.dumps(result, indent=2))

