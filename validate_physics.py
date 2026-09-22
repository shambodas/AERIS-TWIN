#!/usr/bin/env python
"""Comprehensive physics validation after all corrections."""

from engine.atmosphere import ISAAtmosphere
from engine.intake import EngineIntakeModel
from engine.combustion import EngineCombustionModel
from engine.torque import EngineTorqueModel
from engine.propeller import FixedPitchPropellerModel
import math

def test_operating_point(rpm, throttle_pct, altitude_m, airspeed_mps):
    """Test engine at a specific operating point."""
    
    atmosphere = ISAAtmosphere()
    intake = EngineIntakeModel()
    combustion = EngineCombustionModel()
    torque = EngineTorqueModel()
    propeller = FixedPitchPropellerModel()
    
    # Atmosphere
    atm = atmosphere.calculate(altitude_m)
    
    # Intake
    intake_state = intake.calculate(
        throttle_pct=throttle_pct,
        rpm=rpm,
        atmosphere=atm
    )
    
    # Combustion
    comb_state = combustion.calculate(
        intake_state=intake_state,
        rpm=rpm,
        fault_state=None
    )
    
    # Torque
    torque_state = torque.calculate(
        combustion_state=comb_state,
        rpm=rpm,
        manifold_pressure_pa=intake_state.manifold_pressure_pa,
        atmospheric_pressure_pa=atm.pressure_pa
    )
    
    # Propeller
    prop_state = propeller.calculate(
        rpm=rpm,
        forward_velocity_mps=airspeed_mps,
        atmosphere=atm
    )
    
    # Power-torque verification
    omega_rad_s = rpm * 2 * math.pi / 60
    power_from_torque = torque_state.brake_torque_nm * omega_rad_s
    
    return {
        'rpm': rpm,
        'throttle': throttle_pct,
        'altitude': altitude_m,
        'airspeed': airspeed_mps,
        'torque_nm': torque_state.brake_torque_nm,
        'power_w': torque_state.brake_power_w,
        'power_check_w': power_from_torque,
        'prop_load_nm': prop_state.propeller_torque_nm,
        'air_mass_flow': comb_state.air_mass_flow_kg_s,
        'fuel_flow': comb_state.fuel_mass_flow_kg_s,
        'imep_pa': comb_state.imep_pa / 1000,  # kPa
        'manifold_pressure_kpa': intake_state.manifold_pressure_pa / 1000,
        'cht_c': 50,
        'power_error_pct': abs(power_from_torque - torque_state.brake_power_w) / torque_state.brake_power_w * 100 if torque_state.brake_power_w > 0 else 0,
    }

print("=" * 120)
print("AERIS-TWIN PHYSICS VALIDATION")
print("=" * 120)
print()

# Test cases covering typical mission phases
test_points = [
    ("Ground startup", 800, 25, 0, 0),
    ("Ground taxi", 1500, 50, 0, 0),
    ("Takeoff", 6000, 95, 0, 10),
    ("Climb", 5000, 85, 2000, 25),
    ("Cruise", 3000, 70, 5000, 40),
    ("Loiter", 2500, 60, 5000, 30),
    ("Descent", 2000, 50, 3000, 25),
]

for name, rpm, throttle, altitude, airspeed in test_points:
    result = test_operating_point(rpm, throttle, altitude, airspeed)
    print(f"{name:20s} | RPM:{result['rpm']:5.0f} | Throttle:{result['throttle']:5.1f}% | "
          f"Torque:{result['torque_nm']:6.2f}Nm | Power:{result['power_w']/1000:6.2f}kW | "
          f"Prop Load:{result['prop_load_nm']:6.2f}Nm | Air Flow:{result['air_mass_flow']:6.4f}kg/s")

print()
print("DETAILED DIAGNOSTICS - CRUISE POINT (3000 RPM, 70% throttle, 5000m, 40 m/s)")
print("-" * 120)
cruise = test_operating_point(3000, 70, 5000, 40)
for key, value in cruise.items():
    if key not in ['throttle', 'altitude', 'airspeed']:
        if isinstance(value, float):
            print(f"  {key:25s}: {value:12.4f}")
        else:
            print(f"  {key:25s}: {value}")

print()
print("VERIFICATION")
print("-" * 120)
print(f"Power-Torque relationship (P=T×ω) error at cruise: {cruise['power_error_pct']:.4f}%")
print(f"  Engine power: {cruise['power_w']/1000:.2f} kW")
print(f"  Propeller load: {cruise['prop_load_nm']:.2f} Nm")
print(f"  Torque margin: {cruise['torque_nm'] - cruise['prop_load_nm']:.2f} Nm (should be positive)")
print()

# Check ranges
print("EXPECTED RANGES")
print("-" * 120)
print("1200cc naturally-aspirated engine at 3000 RPM, 70% throttle:")
print("  Torque: 20-50 Nm ✓" if 20 <= cruise['torque_nm'] <= 50 else f"  Torque: 20-50 Nm ✗ (got {cruise['torque_nm']:.2f})")
print("  Power: 5-20 kW ✓" if 5 <= cruise['power_w']/1000 <= 20 else f"  Power: 5-20 kW ✗ (got {cruise['power_w']/1000:.2f})")
print("  Air mass flow: 0.015-0.040 kg/s ✓" if 0.015 <= cruise['air_mass_flow'] <= 0.040 else f"  Air mass flow ✗ (got {cruise['air_mass_flow']:.4f})")
print("  IMEP: 800-1200 kPa ✓" if 800 <= cruise['imep_pa'] <= 1200 else f"  IMEP ✗ (got {cruise['imep_pa']:.0f})")
