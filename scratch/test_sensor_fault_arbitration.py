from intelligence.sensor_fault_arbitration import SensorFaultArbitrator
from intelligence.physics_expectation import PhysicsExpectationEngine
from intelligence.deviations import compute_deviations

eng = PhysicsExpectationEngine()
arb = SensorFaultArbitrator()

measured = {
    "rpm": 3000.0,
    "throttle_pct": 50.0,
    "altitude_m": 0.0,
    "ambient_temperature_c": 15.0,
    "cht_cylinder_1_c": 15.0,
    "cht_cylinder_2_c": 15.0,
    "cht_cylinder_3_c": 15.0,
    "cht_cylinder_4_c": 15.0,
    "egt_cylinder_1_c": 15.0,
    "egt_cylinder_2_c": 15.0,
    "egt_cylinder_3_c": 15.0,
    "egt_cylinder_4_c": 15.0,
    "oil_temperature_c": 15.0,
    "oil_pressure_psi": 60.0,
    "vibration_rms": 0.993,
}

expected = eng.calculate(measured_state=measured)
devs = compute_deviations(expected, measured)
result = arb.assess(measured, expected, devs)

print("Expected:", expected)
print("Deviations:", devs)
print("Arbitration:", result)
