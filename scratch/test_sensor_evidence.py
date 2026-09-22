from intelligence.sensor_fault_arbitration import SensorFaultArbitrator
from intelligence.physics_expectation import PhysicsExpectationEngine
from intelligence.deviations import compute_deviations

eng = PhysicsExpectationEngine()
arb = SensorFaultArbitrator()

def test_state(rpm, throttle, cht, egt, oil_temp, oil_press):
    measured = {
        "rpm": rpm,
        "throttle_pct": throttle,
        "altitude_m": 0.0,
        "ambient_temperature_c": 15.0,
        "cht_cylinder_1_c": cht,
        "cht_cylinder_2_c": cht,
        "cht_cylinder_3_c": cht,
        "cht_cylinder_4_c": cht,
        "egt_cylinder_1_c": egt,
        "egt_cylinder_2_c": egt,
        "egt_cylinder_3_c": egt,
        "egt_cylinder_4_c": egt,
        "oil_temperature_c": oil_temp,
        "oil_pressure_psi": oil_press,
        "vibration_rms": 0.993,
    }
    expected = eng.calculate(measured_state=measured)
    devs = compute_deviations(expected, measured)
    result = arb.assess(measured, expected, devs)
    return result['sensor_fault_evidence']

print("Cold, 50% throttle:", test_state(3000, 50, 15, 15, 15, 60))
print("Cold, idle (10%):", test_state(1000, 10, 15, 15, 15, 60))
print("Warm, 90% throttle:", test_state(5000, 90, 80, 200, 80, 60))
print("Warm, idle (10%):", test_state(1000, 10, 80, 200, 80, 60))
