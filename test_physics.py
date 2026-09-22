#!/usr/bin/env python
"""Diagnostic test for physics calculations after displacement fix."""

from engine.atmosphere import ISAAtmosphere
from engine.intake import EngineIntakeModel
from engine.combustion import EngineCombustionModel
from engine.torque import EngineTorqueModel
from simulation.mission import MissionProfile

# Initialize models
atmosphere = ISAAtmosphere()
intake = EngineIntakeModel()
combustion = EngineCombustionModel()
torque = EngineTorqueModel()
mission = MissionProfile()

# Test at ground level, 70% throttle (typical flight)
atm_state = atmosphere.calculate(altitude_m=0.0)
intake_state = intake.calculate(
    throttle_pct=70.0,
    rpm=3000.0,
    atmosphere=atm_state
)
combustion_state = combustion.calculate(
    intake_state=intake_state,
    rpm=3000.0,
    fault_state=None
)
torque_state = torque.calculate(
    combustion_state=combustion_state,
    rpm=3000.0,
    manifold_pressure_pa=intake_state.manifold_pressure_pa,
    atmospheric_pressure_pa=atm_state.pressure_pa
)

print("=" * 80)
print("ENGINE PHYSICS DIAGNOSTIC TEST")
print("=" * 80)
print()

print("CONDITIONS")
print("-" * 80)
print(f"Altitude:           {0.0} m")
print(f"Throttle:           {70.0}%")
print(f"RPM:                {3000.0} RPM")
print()

print("ATMOSPHERE")
print("-" * 80)
print(f"Pressure:           {atm_state.pressure_pa:,.0f} Pa")
print(f"Temperature:        {atm_state.temperature_c:.1f} °C")
print(f"Density:            {atm_state.density_kg_m3:.3f} kg/m³")
print()

print("INTAKE")
print("-" * 80)
print(f"Manifold pressure:  {intake_state.manifold_pressure_pa:,.0f} Pa ({intake_state.manifold_pressure_pa/1000:.1f} kPa)")
print(f"Manifold temp:      {intake_state.manifold_temperature_k - 273.15:.1f} °C")
print(f"Volumetric eff:     {intake_state.volumetric_efficiency:.3f}")
print(f"Cylinder air/cyc:   {intake_state.cylinder_air_charge_kg:.6f} kg")
print(f"Air mass flow:      {intake_state.air_mass_flow_kg_s:.6f} kg/s")
print()

print("COMBUSTION")
print("-" * 80)
print(f"Air mass flow:      {combustion_state.air_mass_flow_kg_s:.6f} kg/s")
print(f"Fuel mass flow:     {combustion_state.fuel_mass_flow_kg_s:.6f} kg/s")
print(f"AFR:                {combustion_state.afr:.2f}")
print(f"Combustion eff:     {combustion_state.combustion_efficiency:.3f}")
print(f"IMEP:               {combustion_state.imep_pa:,.0f} Pa ({combustion_state.imep_pa/1000:.1f} kPa)")
print(f"Indicated power:    {combustion_state.indicated_power_w:.1f} W ({combustion_state.indicated_power_w/1000:.2f} kW)")
print(f"Heat release rate:  {combustion_state.total_heat_release_w:.1f} W ({combustion_state.total_heat_release_w/1000:.2f} kW)")
print()

print("TORQUE / MECHANICAL")
print("-" * 80)
print(f"IMEP:               {torque_state.imep_pa:,.0f} Pa")
print(f"FMEP:               {torque_state.fmep_pa:,.0f} Pa")
print(f"Pumping MEP:        {torque_state.pumping_mep_pa:,.0f} Pa")
print(f"BMEP:               {torque_state.bmep_pa:,.0f} Pa")
print(f"Indicated torque:   {torque_state.indicated_torque_nm:.2f} Nm")
print(f"Brake torque:       {torque_state.brake_torque_nm:.2f} Nm")
print(f"Brake power:        {torque_state.brake_power_w:.1f} W ({torque_state.brake_power_w/1000:.2f} kW)")
print(f"Mechanical eff:     {torque_state.mechanical_efficiency:.3f}")
print()

print("EXPECTED RANGES FOR TYPICAL 1200CC ENGINE")
print("-" * 80)
print(f"Torque:             20-50 Nm (depending on throttle/RPM)")
print(f"Power:              15-50 kW (depending on throttle/RPM)")
print()

print("UNIT VERIFICATION")
print("-" * 80)
omega_rads = 3000 * 2 * 3.14159 / 60
print(f"RPM:                {3000} RPM")
print(f"Angular velocity:   {omega_rads:.2f} rad/s")
power_check = torque_state.brake_torque_nm * omega_rads
print(f"Power check (T*omega):  {power_check:.1f} W ({power_check/1000:.2f} kW)")
print(f"Power from model:   {torque_state.brake_power_w:.1f} W ({torque_state.brake_power_w/1000:.2f} kW)")
print(f"Match: {'YES' if abs(power_check - torque_state.brake_power_w) < 1 else 'NO (ERROR)'}")
