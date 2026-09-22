"""
AERIS-TWIN
Atmospheric / Flight Environment Model

Purpose:
    Calculate atmospheric boundary conditions for the virtual
    aero-piston engine.

Model:
    Standard ISA troposphere approximation.

Outputs:
    - Temperature
    - Pressure
    - Air density
    - Density ratio
    - Speed of sound

All SI units are used internally.
"""

from dataclasses import dataclass
import math


# ============================================================
# CONSTANTS
# ============================================================

SEA_LEVEL_TEMPERATURE_K = 288.15       # K
SEA_LEVEL_PRESSURE_PA = 101325.0       # Pa
SEA_LEVEL_DENSITY = 1.225              # kg/m^3

TEMPERATURE_LAPSE_RATE = 0.0065        # K/m
GRAVITY = 9.80665                      # m/s^2
AIR_GAS_CONSTANT = 287.05287           # J/(kg*K)

TROPOSPHERE_LIMIT_M = 11000.0


# ============================================================
# DATA STRUCTURE
# ============================================================

@dataclass
class AtmosphericState:
    """
    Atmospheric state at a given altitude.
    """

    altitude_m: float
    temperature_k: float
    pressure_pa: float
    density_kg_m3: float
    density_ratio: float
    speed_of_sound_mps: float

    @property
    def temperature_c(self) -> float:
        """Temperature in degrees Celsius."""
        return self.temperature_k - 273.15


# ============================================================
# ATMOSPHERE MODEL
# ============================================================

class ISAAtmosphere:
    """
    International Standard Atmosphere approximation.

    Current implementation covers the troposphere, which is
    sufficient for the intended MALE-UAV piston-engine
    operating envelope.

    The model is intentionally independent of the engine model.
    This allows the same atmosphere model to be reused by:

        atmosphere
            ↓
        intake
            ↓
        combustion
            ↓
        engine dynamics
    """

    def __init__(
        self,
        sea_level_temperature_k: float = SEA_LEVEL_TEMPERATURE_K,
        sea_level_pressure_pa: float = SEA_LEVEL_PRESSURE_PA,
    ):

        self.T0 = sea_level_temperature_k
        self.P0 = sea_level_pressure_pa

        self.rho0 = (
            self.P0
            / (AIR_GAS_CONSTANT * self.T0)
        )


    # ========================================================
    # ATMOSPHERIC STATE
    # ========================================================

    def calculate(
        self,
        altitude_m: float,
        temperature_offset_k: float = 0.0,
    ) -> AtmosphericState:
        """
        Calculate atmospheric conditions.

        Parameters
        ----------
        altitude_m:
            Geometric altitude in metres.

        temperature_offset_k:
            Optional deviation from ISA temperature.
            Useful for modelling hot/cold mission conditions.

        Returns
        -------
        AtmosphericState
        """

        altitude_m = max(
            0.0,
            altitude_m
        )

        # ----------------------------------------------------
        # Troposphere
        # ----------------------------------------------------

        if altitude_m <= TROPOSPHERE_LIMIT_M:

            # Standard ISA temperature at this altitude (no weather offset)
            isa_temperature_k = (
                self.T0
                - TEMPERATURE_LAPSE_RATE * altitude_m
            )

            # Pressure follows the standard ISA hydrostatic column.
            # The weather offset does NOT alter pressure — only density
            # responds via the ideal-gas law once temperature is adjusted.
            exponent = (
                GRAVITY
                / (
                    AIR_GAS_CONSTANT
                    * TEMPERATURE_LAPSE_RATE
                )
            )

            pressure_pa = (
                self.P0
                * (
                    isa_temperature_k
                    / self.T0
                ) ** exponent
            )

            # Apply mission/weather temperature deviation after pressure is set
            temperature_k = max(
                150.0,
                isa_temperature_k + temperature_offset_k,
            )

        else:

            # ------------------------------------------------
            # For now, hold the ISA temperature at the
            # tropopause and use the isothermal relationship.
            #
            # This keeps the model numerically stable if a
            # future simulation requests an altitude above
            # the MALE-UAV piston-engine operating region.
            # ------------------------------------------------

            # Standard ISA tropopause temperature (no weather offset)
            isa_tropopause_temperature = max(
                150.0,
                self.T0
                - TEMPERATURE_LAPSE_RATE
                * TROPOSPHERE_LIMIT_M
            )

            # Pressure uses the standard ISA tropopause temperature only
            pressure_at_tropopause = (
                self.P0
                * (
                    isa_tropopause_temperature
                    / self.T0
                ) ** (
                    GRAVITY
                    / (
                        AIR_GAS_CONSTANT
                        * TEMPERATURE_LAPSE_RATE
                    )
                )
            )

            height_above_tropopause = (
                altitude_m
                - TROPOSPHERE_LIMIT_M
            )

            # Apply weather offset to temperature only (after pressure is set)
            temperature_k = max(
                150.0,
                isa_tropopause_temperature + temperature_offset_k,
            )

            pressure_pa = (
                pressure_at_tropopause
                * math.exp(
                    -GRAVITY
                    * height_above_tropopause
                    / (
                        AIR_GAS_CONSTANT
                        * temperature_k
                    )
                )
            )

        # ----------------------------------------------------
        # Density
        # ----------------------------------------------------

        density_kg_m3 = (
            pressure_pa
            / (
                AIR_GAS_CONSTANT
                * temperature_k
            )
        )

        density_ratio = (
            density_kg_m3
            / self.rho0
        )

        # ----------------------------------------------------
        # Speed of sound
        # ----------------------------------------------------

        # Approximation for dry air.
        gamma = 1.4

        speed_of_sound_mps = math.sqrt(
            gamma
            * AIR_GAS_CONSTANT
            * temperature_k
        )

        return AtmosphericState(

            altitude_m=altitude_m,

            temperature_k=temperature_k,

            pressure_pa=pressure_pa,

            density_kg_m3=density_kg_m3,

            density_ratio=density_ratio,

            speed_of_sound_mps=speed_of_sound_mps,
        )


# ============================================================
# SIMPLE TEST
# ============================================================

if __name__ == "__main__":

    atmosphere = ISAAtmosphere()

    test_altitudes = [
        0,
        1000,
        3000,
        5000,
        6000,
    ]

    print("\nAERIS-TWIN ATMOSPHERE MODEL")
    print("=" * 72)

    for altitude in test_altitudes:

        state = atmosphere.calculate(
            altitude_m=altitude
        )

        print(
            f"Altitude: {state.altitude_m:6.0f} m | "
            f"T: {state.temperature_c:6.2f} °C | "
            f"P: {state.pressure_pa:9.0f} Pa | "
            f"ρ: {state.density_kg_m3:.4f} kg/m³ | "
            f"ρ/ρ0: {state.density_ratio:.3f} | "
            f"a: {state.speed_of_sound_mps:.1f} m/s"
        )

    print("\nHot-weather example at 3000 m:")

    hot_state = atmosphere.calculate(
        altitude_m=3000,
        temperature_offset_k=20.0
    )

    print(
        f"T: {hot_state.temperature_c:.2f} °C | "
        f"Density ratio: {hot_state.density_ratio:.3f}"
    )