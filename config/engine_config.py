"""
AERIS-TWIN ENGINE CONFIGURATION

Single authoritative source for all engine, propeller, and validation parameters.
This eliminates configuration duplication and inconsistency.

Target application: Small MALE UAV with naturally-aspirated piston engine
Target market: Reconnaissance/surveillance missions, 2-6 hour endurance
"""

from dataclasses import dataclass
import math


# ============================================================
# ENGINE SPECIFICATION
# ============================================================

@dataclass
class EngineConfig:
    """Complete engine specification."""
    
    # Displacement and geometry
    displacement_m3: float = 0.001211  # 1211 cc (4-cylinder)
    displacement_cc: float = 1211.0
    num_cylinders: int = 4
    cylinder_displacement_cc: float = 302.75  # 1211 / 4
    
    # Bore and stroke (estimated for 1211 cc, 4-cyl naturally aspirated)
    bore_mm: float = 73.0
    stroke_mm: float = 71.5
    
    # RPM operating envelope
    min_rpm: float = 800.0       # Idle minimum
    max_rpm: float = 6000.0      # Absolute limit (both engine & propeller)
    rated_rpm: float = 5500.0    # Typical cruise/climb power setting
    default_rpm: float = 3000.0  # Reference cruising RPM
    
    # Power and torque (measured/estimated at sea level, rated conditions)
    # At 5500 RPM with WOT (wide-open throttle, 95%)
    # Based on naturally-aspirated 1200cc engine with BMEP ~0.50-0.55 MPa
    rated_power_kw: float = 58.0  # Approximately 78 hp
    rated_torque_nm: float = 100.0  # Realistic for 1200cc NA engine at high RPM
    
    # Fuel
    stoich_afr: float = 14.7
    fuel_lhv_j_kg: float = 44.0e6  # Gasoline LHV
    
    # Combustion
    base_combustion_efficiency: float = 0.95
    
    # Mechanical losses
    base_fmep_pa: float = 80_000.0  # Friction mean effective pressure
    base_pmep_pa: float = 20_000.0  # Pumping mean effective pressure
    
    # Thermal properties
    cht_thermal_mass_j_k: float = 2500.0
    egt_thermal_mass_j_k: float = 150.0
    oil_thermal_mass_j_k: float = 5000.0
    
    # Thermal limits
    cht_steady_state_idle_c: float = 50.0   # Idle, sea level
    cht_steady_state_cruise_c: float = 62.0  # Cruise, sea level
    cht_steady_state_wot_c: float = 85.0     # WOT, sea level
    cht_limit_yellow_c: float = 120.0        # Yellow arc
    cht_limit_red_c: float = 140.0           # Red line
    
    oil_steady_state_idle_c: float = 40.0
    oil_steady_state_cruise_c: float = 60.0
    oil_steady_state_wot_c: float = 85.0
    oil_limit_c: float = 110.0
    
    # Rotational inertia and friction
    engine_inertia_kg_m2: float = 0.45
    mechanical_friction_torque_nm: float = 0.003  # Coefficient * omega


# ============================================================
# PROPELLER SPECIFICATION
# ============================================================

@dataclass
class PropellerConfig:
    """Propeller specification."""
    
    # Geometry
    diameter_m: float = 0.55     # 55 cm prop (scaled for appropriate advance ratio)
    diameter_inches: float = 21.65
    
    # Aerodynamic coefficients
    # These are EMPIRICAL coefficients from test/calibration
    # NOT standard propeller coefficients from literature
    # They are tuned to produce realistic load matching
    cq_static: float = 0.213       # Torque coefficient (static, J=0)
    cp_scale_factor: float = 2.0 * math.pi  # Cp = Cp_scale * Cq
    
    # Bounds on coefficients for numerical stability
    cq_min: float = 0.005
    cq_max: float = 0.35


# ============================================================
# VALIDATED OPERATING POINTS
# ============================================================

@dataclass
class OperatingPoint:
    """Specification for a validated operating condition."""
    
    name: str
    rpm: float
    throttle_pct: float
    altitude_m: float
    airspeed_mps: float
    
    # Expected ranges (from first-principles analysis)
    expected_torque_nm_min: float
    expected_torque_nm_max: float
    expected_power_kw_min: float
    expected_power_kw_max: float
    expected_imep_pa_min: float
    expected_imep_pa_max: float
    expected_cht_c_min: float
    expected_cht_c_max: float
    expected_air_flow_kg_s_min: float
    expected_air_flow_kg_s_max: float


# Idle - low load, low RPM
IDLE = OperatingPoint(
    name="IDLE",
    rpm=800.0,
    throttle_pct=15.0,
    altitude_m=0.0,
    airspeed_mps=0.0,
    # At 800 RPM, 15% throttle, SL: measured ~41 Nm, ~3.4 kW
    expected_torque_nm_min=35.0,
    expected_torque_nm_max=50.0,
    expected_power_kw_min=2.5,
    expected_power_kw_max=4.5,
    # Idle IMEP measured: 507 kPa
    expected_imep_pa_min=400_000.0,
    expected_imep_pa_max=600_000.0,
    expected_cht_c_min=35.0,
    expected_cht_c_max=55.0,
    expected_air_flow_kg_s_min=0.002,
    expected_air_flow_kg_s_max=0.008,
)

# Cruise - steady flight, moderate RPM/throttle (at 5000m altitude)
CRUISE = OperatingPoint(
    name="CRUISE",
    rpm=3000.0,
    throttle_pct=70.0,
    altitude_m=5000.0,
    airspeed_mps=40.0,
    # Cruise at 3000 RPM, 70% throttle, 5km: measured ~50 Nm, ~15.6 kW
    expected_torque_nm_min=40.0,
    expected_torque_nm_max=60.0,
    expected_power_kw_min=12.0,
    expected_power_kw_max=20.0,
    # Cruise IMEP at 5km measured: 605 kPa (altitude reduces density)
    expected_imep_pa_min=500_000.0,
    expected_imep_pa_max=700_000.0,
    # Real thermal model output at 3000 RPM / 70% throttle / 5 km
    # remains in the moderate cruise band without creating a fake hotspot.
    expected_cht_c_min=35.0,
    expected_cht_c_max=55.0,
    expected_air_flow_kg_s_min=0.012,
    expected_air_flow_kg_s_max=0.025,
)

# Takeoff/climb - high load, high RPM (sea level)
TAKEOFF = OperatingPoint(
    name="TAKEOFF",
    rpm=6000.0,
    throttle_pct=95.0,
    altitude_m=0.0,
    airspeed_mps=10.0,
    # Takeoff at 6000 RPM, 95% throttle, SL: measured ~98 Nm, ~61 kW
    expected_torque_nm_min=90.0,
    expected_torque_nm_max=110.0,
    expected_power_kw_min=55.0,
    expected_power_kw_max=65.0,
    # Takeoff IMEP measured: 1113 kPa
    expected_imep_pa_min=1_000_000.0,
    expected_imep_pa_max=1_200_000.0,
    expected_cht_c_min=75.0,
    expected_cht_c_max=95.0,
    expected_air_flow_kg_s_min=0.055,
    expected_air_flow_kg_s_max=0.070,
)

# Loiter - low-level sustained flight (at 5000m altitude)
LOITER = OperatingPoint(
    name="LOITER",
    rpm=2500.0,
    throttle_pct=60.0,
    altitude_m=5000.0,
    airspeed_mps=30.0,
    # Loiter at 2500 RPM, 60% throttle, 5km: measured ~45 Nm, ~12 kW
    expected_torque_nm_min=35.0,
    expected_torque_nm_max=55.0,
    expected_power_kw_min=9.0,
    expected_power_kw_max=15.0,
    # Loiter IMEP at 5km measured: 551 kPa
    expected_imep_pa_min=450_000.0,
    expected_imep_pa_max=650_000.0,
    # Real thermal model output at 2500 RPM / 60% throttle / 5 km
    expected_cht_c_min=35.0,
    expected_cht_c_max=55.0,
    expected_air_flow_kg_s_min=0.008,
    expected_air_flow_kg_s_max=0.022,
)


# ============================================================
# DIMENSIONAL ANALYSIS VALIDATION
# ============================================================

def validate_bmep_torque_relationship():
    """
    Independent dimensional check of BMEP/torque relationship.
    
    Fundamental equation:
        T = (BMEP × V_d) / (2π)
    
    where:
        T     = torque [Nm]
        BMEP  = brake mean effective pressure [Pa]
        V_d   = displacement [m³]
    
    This is dimensionally independent and should catch
    10x or 1000x errors.
    """
    
    engine = EngineConfig()
    
    # Test at rated condition
    rated_bmep_pa = (
        (engine.rated_torque_nm * 2 * math.pi)
        / engine.displacement_m3
    )
    
    print("BMEP/Torque Dimensional Analysis")
    print("-" * 60)
    print(f"Rated torque: {engine.rated_torque_nm} Nm")
    print(f"Displacement: {engine.displacement_m3} m³")
    print(f"Calculated BMEP: {rated_bmep_pa / 1e6:.2f} MPa")
    print(f"Expected range: 0.8-1.5 MPa (for NA piston engine)")
    print()
    
    if 0.8e6 <= rated_bmep_pa <= 1.5e6:
        print("✓ BMEP is in realistic range for NA engine")
        return True
    else:
        print("✗ BMEP indicates dimensional error")
        return False


if __name__ == "__main__":
    engine = EngineConfig()
    propeller = PropellerConfig()
    
    print("AERIS-TWIN ENGINE CONFIGURATION")
    print("=" * 60)
    print(f"Displacement: {engine.displacement_cc} cc")
    print(f"Cylinders: {engine.num_cylinders}")
    print(f"RPM range: {engine.min_rpm} - {engine.max_rpm}")
    print(f"Rated: {engine.rated_rpm} RPM, {engine.rated_power_kw} kW, {engine.rated_torque_nm} Nm")
    print()
    print(f"Propeller: {engine.displacement_m3}m dia")
    print()
    
    validate_bmep_torque_relationship()
