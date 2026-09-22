"""
AERIS-TWIN
Engine Intake / Air-Charge Model

Purpose
-------
Calculate the engine air-charge characteristics from:

    - Throttle position
    - Engine speed
    - Atmospheric pressure
    - Atmospheric temperature
    - Air density

Outputs
-------
    - Throttle effective area
    - Manifold pressure
    - Manifold temperature
    - Volumetric efficiency
    - Cylinder air charge
    - Total air mass flow

Model type
----------
Reduced-order engineering mean-value model.

The model is designed to provide a physically consistent
interface between the atmospheric model and combustion model.

Flow:

    Atmosphere
        ↓
    Intake
        ↓
    Air mass flow
        ↓
    Combustion
"""

from dataclasses import dataclass
import math

from engine.atmosphere import AtmosphericState


# ============================================================
# CONSTANTS
# ============================================================

# Specific gas constant for air
R_AIR = 287.05287       # J/(kg*K)

# Ratio of specific heats
GAMMA_AIR = 1.40

# Four-stroke engine
FOUR_STROKE = 4.0

# Representative engine displacement (1.211 liters / 1211 cc).
#
# This is a configurable representative value for a typical
# small aero piston engine suitable for MALE UAVs.
ENGINE_DISPLACEMENT_M3 = 0.001211

# Intake manifold temperature rise / loss model
MIN_MANIFOLD_TEMPERATURE_K = 240.0

# Minimum physically meaningful manifold pressure
MIN_MANIFOLD_PRESSURE_PA = 20_000.0


# ============================================================
# DATA STRUCTURE
# ============================================================

@dataclass
class IntakeState:
    """
    Calculated engine intake state.
    """

    throttle_pct: float

    throttle_fraction: float

    manifold_pressure_pa: float

    manifold_temperature_k: float

    manifold_density_kg_m3: float

    volumetric_efficiency: float

    cylinder_air_charge_kg: float

    air_mass_flow_kg_s: float


# ============================================================
# INTAKE MODEL
# ============================================================

class EngineIntakeModel:
    """
    Mean-value engine intake model.

    The model represents the intake system without attempting
    to resolve individual intake-valve flow events.

    This is appropriate for a real-time Digital Twin where
    computational efficiency and stable telemetry generation
    are important.
    """

    def __init__(
        self,
        displacement_m3: float = ENGINE_DISPLACEMENT_M3,
    ):

        if displacement_m3 <= 0:

            raise ValueError(
                "Engine displacement must be positive."
            )

        self.displacement_m3 = displacement_m3


    # ========================================================
    # THROTTLE MODEL
    # ========================================================

    @staticmethod
    def _normalise_throttle(
        throttle_pct: float
    ) -> float:
        """
        Convert throttle percentage to [0, 1].
        """

        throttle_pct = max(
            0.0,
            min(100.0, throttle_pct)
        )

        return throttle_pct / 100.0


    # ========================================================
    # MANIFOLD PRESSURE
    # ========================================================

    @staticmethod
    def _calculate_manifold_pressure(
        atmosphere: AtmosphericState,
        throttle_fraction: float,
    ) -> float:
        """
        Estimate intake manifold absolute pressure.

        A simple pressure recovery relationship is used:

            MAP = P_atm * f(throttle)

        A non-zero closed-throttle pressure is retained to
        represent engine pumping/vacuum behaviour.

        This is intentionally a mean-value approximation.
        """

        # Residual pressure at closed throttle.
        closed_throttle_ratio = 0.28

        # Nonlinear throttle response.
        #
        # The exponent prevents manifold pressure from rising
        # unrealistically linearly with throttle.
        throttle_pressure_ratio = (
            closed_throttle_ratio
            + (
                1.0 - closed_throttle_ratio
            )
            * throttle_fraction ** 0.65
        )

        manifold_pressure = (
            atmosphere.pressure_pa
            * throttle_pressure_ratio
        )

        return max(
            MIN_MANIFOLD_PRESSURE_PA,
            manifold_pressure
        )


    # ========================================================
    # MANIFOLD TEMPERATURE
    # ========================================================

    @staticmethod
    def _calculate_manifold_temperature(
        atmosphere: AtmosphericState,
        manifold_pressure_pa: float,
    ) -> float:
        """
        Estimate manifold temperature.

        Lower manifold pressure can produce some charge
        cooling due to pressure reduction.

        The effect is deliberately bounded because this is
        not a detailed intake-flow CFD model.
        """

        pressure_ratio = (
            manifold_pressure_pa
            / atmosphere.pressure_pa
        )

        pressure_ratio = max(
            0.1,
            min(1.0, pressure_ratio)
        )

        # Isentropic temperature relationship
        temperature_ratio = (
            pressure_ratio
            ** (
                (GAMMA_AIR - 1.0)
                / GAMMA_AIR
            )
        )

        ideal_temperature = (
            atmosphere.temperature_k
            * temperature_ratio
        )

        # Mix ideal pressure cooling with a small recovery
        # toward ambient temperature.
        manifold_temperature = (
            0.70 * ideal_temperature
            + 0.30 * atmosphere.temperature_k
        )

        return max(
            MIN_MANIFOLD_TEMPERATURE_K,
            manifold_temperature
        )


    # ========================================================
    # VOLUMETRIC EFFICIENCY
    # ========================================================

    @staticmethod
    def _calculate_volumetric_efficiency(
        rpm: float,
        manifold_pressure_pa: float,
        atmospheric_pressure_pa: float,
    ) -> float:
        """
        Estimate volumetric efficiency.

        Volumetric efficiency varies with engine speed and
        intake pressure.

        A broad bell-shaped speed response is used to represent
        the behaviour of a naturally aspirated piston engine.

        Returns:
            Dimensionless efficiency, approximately 0.65–0.95.
        """

        rpm = max(
            0.0,
            rpm
        )

        # Representative peak-efficiency region.
        peak_rpm = 4200.0

        # Speed penalty around the peak.
        speed_ratio = (
            rpm / peak_rpm
        )

        speed_factor = math.exp(
            -0.5
            * (
                (speed_ratio - 1.0)
                / 0.65
            ) ** 2
        )

        # Base efficiency plus speed-dependent improvement.
        eta_v = (
            0.62
            + 0.30 * speed_factor
        )

        # Naturally aspirated engines lose effective charge
        # with reduced manifold pressure.
        pressure_ratio = (
            manifold_pressure_pa
            / max(
                atmospheric_pressure_pa,
                1.0
            )
        )

        pressure_ratio = max(
            0.20,
            min(1.0, pressure_ratio)
        )

        eta_v *= (
            0.80
            + 0.20 * pressure_ratio
        )

        return max(
            0.45,
            min(0.98, eta_v)
        )


    # ========================================================
    # CYLINDER AIR CHARGE
    # ========================================================

    def _calculate_cylinder_air_charge(
        self,
        manifold_pressure_pa: float,
        manifold_temperature_k: float,
        volumetric_efficiency: float,
    ) -> float:
        """
        Calculate air mass inducted per engine cycle.

        Ideal gas:

            m = P V / R T

        Volumetric efficiency is applied to the geometric
        cylinder volume.
        """

        total_charge = (
            manifold_pressure_pa
            * self.displacement_m3
            * volumetric_efficiency
            / (
                R_AIR
                * manifold_temperature_k
            )
        )

        return max(
            0.0,
            total_charge
        )


    # ========================================================
    # MASS FLOW
    # ========================================================

    def _calculate_air_mass_flow(
        self,
        cylinder_air_charge_kg: float,
        rpm: float,
    ) -> float:
        """
        Calculate total engine air mass flow.

        For a four-stroke engine:

            cycles/sec = RPM / (2 * 60)

        Therefore:

            mdot = m_cycle * RPM / 120
        """

        rpm = max(
            0.0,
            rpm
        )

        cycles_per_second = (
            rpm
            / 120.0
        )

        air_mass_flow = (
            cylinder_air_charge_kg
            * cycles_per_second
        )

        return max(
            0.0,
            air_mass_flow
        )


    # ========================================================
    # MAIN CALCULATION
    # ========================================================

    def calculate(
        self,
        throttle_pct: float,
        rpm: float,
        atmosphere: AtmosphericState,
    ) -> IntakeState:
        """
        Calculate the complete intake state.

        Parameters
        ----------
        throttle_pct:
            Throttle command from 0–100%.

        rpm:
            Engine rotational speed.

        atmosphere:
            AtmosphericState generated by atmosphere.py.

        Returns
        -------
        IntakeState
        """

        throttle_pct = max(
            0.0,
            min(100.0, throttle_pct)
        )

        rpm = max(
            0.0,
            rpm
        )

        throttle_fraction = (
            self._normalise_throttle(
                throttle_pct
            )
        )

        # ----------------------------------------------------
        # 1. Manifold pressure
        # ----------------------------------------------------

        manifold_pressure = (
            self._calculate_manifold_pressure(
                atmosphere,
                throttle_fraction
            )
        )

        # ----------------------------------------------------
        # 2. Manifold temperature
        # ----------------------------------------------------

        manifold_temperature = (
            self._calculate_manifold_temperature(
                atmosphere,
                manifold_pressure
            )
        )

        # ----------------------------------------------------
        # 3. Volumetric efficiency
        # ----------------------------------------------------

        volumetric_efficiency = (
            self._calculate_volumetric_efficiency(
                rpm,
                manifold_pressure,
                atmosphere.pressure_pa,
            )
        )

        # ----------------------------------------------------
        # 4. Manifold density
        # ----------------------------------------------------

        manifold_density = (
            manifold_pressure
            / (
                R_AIR
                * manifold_temperature
            )
        )

        # ----------------------------------------------------
        # 5. Cylinder air charge
        # ----------------------------------------------------

        cylinder_air_charge = (
            self._calculate_cylinder_air_charge(
                manifold_pressure,
                manifold_temperature,
                volumetric_efficiency,
            )
        )

        # ----------------------------------------------------
        # 6. Air mass flow
        # ----------------------------------------------------

        air_mass_flow = (
            self._calculate_air_mass_flow(
                cylinder_air_charge,
                rpm,
            )
        )

        return IntakeState(

            throttle_pct=throttle_pct,

            throttle_fraction=throttle_fraction,

            manifold_pressure_pa=(
                manifold_pressure
            ),

            manifold_temperature_k=(
                manifold_temperature
            ),

            manifold_density_kg_m3=(
                manifold_density
            ),

            volumetric_efficiency=(
                volumetric_efficiency
            ),

            cylinder_air_charge_kg=(
                cylinder_air_charge
            ),

            air_mass_flow_kg_s=(
                air_mass_flow
            ),
        )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    from engine.atmosphere import ISAAtmosphere

    atmosphere_model = ISAAtmosphere()

    intake_model = EngineIntakeModel()

    environment = atmosphere_model.calculate(
        altitude_m=3000.0
    )

    print("\nAERIS-TWIN INTAKE MODEL")
    print("=" * 80)

    print(
        f"Atmosphere: "
        f"{environment.temperature_c:.2f} °C | "
        f"{environment.pressure_pa:.0f} Pa | "
        f"ρ = "
        f"{environment.density_kg_m3:.3f} kg/m³"
    )

    print()

    for throttle in [
        20.0,
        40.0,
        60.0,
        80.0,
        100.0,
    ]:

        state = intake_model.calculate(
            throttle_pct=throttle,
            rpm=4000.0,
            atmosphere=environment,
        )

        print(
            f"Throttle: "
            f"{state.throttle_pct:5.1f}% | "
            f"MAP: "
            f"{state.manifold_pressure_pa / 1000:7.2f} kPa | "
            f"VE: "
            f"{state.volumetric_efficiency:.3f} | "
            f"Air Flow: "
            f"{state.air_mass_flow_kg_s:.4f} kg/s"
        )