"""
AERIS-TWIN
Engine Torque / Mechanical Dynamics Model

Purpose
-------
Convert combustion pressure/work into useful mechanical
engine output.

Flow:

    IMEP
      ↓
    FMEP
      ↓
    BMEP
      ↓
    Brake Torque
      ↓
    Brake Power

The model also calculates angular acceleration from:

    Engine Torque
        -
    Propeller Load
        -
    Mechanical Losses

This module does NOT calculate propeller aerodynamic load.
That is handled separately by propeller.py.

Model type
----------
Engineering mean-value mechanical model.

All internal mechanical calculations use SI units.
"""


from dataclasses import dataclass
import math

from engine.combustion import CombustionState


# ============================================================
# CONSTANTS
# ============================================================

# Four-stroke engine
FOUR_STROKE = 4.0

# Reference atmospheric pressure
REFERENCE_PRESSURE_PA = 101325.0

# Representative friction MEP at low/moderate speed
BASE_FMEP_PA = 80_000.0

# Speed-dependent friction coefficient
FMEP_SPEED_COEFFICIENT = 15_000.0

# Additional pumping-loss contribution
BASE_PUMPING_MEP_PA = 15_000.0

# Mechanical efficiency limits
MIN_MECHANICAL_EFFICIENCY = 0.70
MAX_MECHANICAL_EFFICIENCY = 0.97

# Numerical safety limits (must match engine_simulator.py and config)
# See: config/engine_config.py for authoritative engine specifications
MIN_RPM = 800.0
MAX_RPM = 6000.0


# ============================================================
# DATA STRUCTURE
# ============================================================

@dataclass
class TorqueState:
    """
    Mechanical state of the engine.
    """

    rpm: float

    omega_rads: float

    imep_pa: float

    fmep_pa: float

    pumping_mep_pa: float

    bmep_pa: float

    indicated_power_w: float

    brake_power_w: float

    indicated_torque_nm: float

    brake_torque_nm: float

    mechanical_efficiency: float


# ============================================================
# TORQUE MODEL
# ============================================================

class EngineTorqueModel:
    """
    Converts cylinder combustion output into brake torque
    and brake power.

    Mechanical losses are represented using a speed-dependent
    FMEP model.

    BMEP is calculated as:

        BMEP = IMEP - FMEP - PMEP

    For a four-stroke engine:

        T = BMEP * Vd / (4π)

    where:

        Vd = total engine displacement.
    """

    def __init__(
        self,
        displacement_m3: float = 0.001211,
    ):

        if displacement_m3 <= 0:

            raise ValueError(
                "Engine displacement must be positive."
            )

        self.displacement_m3 = (
            displacement_m3
        )


    # ========================================================
    # RPM / ANGULAR VELOCITY
    # ========================================================

    @staticmethod
    def rpm_to_omega(
        rpm: float
    ) -> float:
        """
        Convert RPM to angular velocity.

            ω = RPM × 2π / 60
        """

        rpm = max(
            0.0,
            rpm
        )

        return (
            rpm
            * 2.0
            * math.pi
            / 60.0
        )


    @staticmethod
    def omega_to_rpm(
        omega_rads: float
    ) -> float:
        """
        Convert angular velocity to RPM.
        """

        omega_rads = max(
            0.0,
            omega_rads
        )

        return (
            omega_rads
            * 60.0
            / (2.0 * math.pi)
        )


    # ========================================================
    # FMEP
    # ========================================================

    @staticmethod
    def calculate_fmep(
        rpm: float
    ) -> float:
        """
        Estimate friction mean effective pressure.

        The model increases friction losses with engine speed.

        This is a reduced-order representation of losses from:

            - piston/ring friction
            - bearings
            - valvetrain
            - oil pumping

        Returns:
            FMEP in Pa.
        """

        rpm = max(
            0.0,
            rpm
        )

        speed_ratio = (
            rpm / 5000.0
        )

        fmep = (
            BASE_FMEP_PA
            + FMEP_SPEED_COEFFICIENT
            * speed_ratio ** 1.5
        )

        return max(
            0.0,
            fmep
        )


    # ========================================================
    # PUMPING MEP
    # ========================================================

    @staticmethod
    def calculate_pumping_mep(
        rpm: float,
        manifold_pressure_pa: float,
        atmospheric_pressure_pa: float,
    ) -> float:
        """
        Estimate pumping losses.

        Pumping loss becomes more important when manifold
        pressure is substantially below atmospheric pressure.

        This is particularly relevant at partial throttle.
        """

        atmospheric_pressure_pa = max(
            atmospheric_pressure_pa,
            1.0
        )

        manifold_pressure_pa = max(
            manifold_pressure_pa,
            1.0
        )

        pressure_drop_ratio = max(
            0.0,
            1.0
            - (
                manifold_pressure_pa
                / atmospheric_pressure_pa
            )
        )

        speed_factor = max(
            0.2,
            min(
                2.0,
                rpm / 4000.0
            )
        )

        pumping_mep = (
            BASE_PUMPING_MEP_PA
            * pressure_drop_ratio
            * speed_factor
        )

        return max(
            0.0,
            pumping_mep
        )


    # ========================================================
    # BMEP
    # ========================================================

    @staticmethod
    def calculate_bmep(
        imep_pa: float,
        fmep_pa: float,
        pumping_mep_pa: float,
    ) -> float:
        """
        Calculate brake mean effective pressure.

            BMEP = IMEP - FMEP - PMEP
        """

        bmep = (
            imep_pa
            - fmep_pa
            - pumping_mep_pa
        )

        return max(
            0.0,
            bmep
        )


    # ========================================================
    # TORQUE FROM MEP
    # ========================================================

    def calculate_torque_from_mep(
        self,
        mep_pa: float,
    ) -> float:
        """
        Calculate torque from mean effective pressure.

        For a four-stroke engine:

            W_cycle = BMEP × Vd

        and:

            W_cycle = T × 4π

        therefore:

            T = BMEP × Vd / (4π)
        """

        return (
            mep_pa
            * self.displacement_m3
            / (
                4.0
                * math.pi
            )
        )


    # ========================================================
    # POWER
    # ========================================================

    @staticmethod
    def calculate_power(
        torque_nm: float,
        omega_rads: float,
    ) -> float:
        """
        Mechanical power:

            P = Tω
        """

        return max(
            0.0,
            torque_nm
            * omega_rads
        )


    # ========================================================
    # MAIN CALCULATION
    # ========================================================

    def calculate(
        self,
        combustion_state: CombustionState,
        rpm: float,
        manifold_pressure_pa: float,
        atmospheric_pressure_pa: float,
    ) -> TorqueState:
        """
        Calculate complete engine mechanical output.

        Parameters
        ----------
        combustion_state:
            Output from combustion.py.

        rpm:
            Current engine speed.

        manifold_pressure_pa:
            Intake manifold absolute pressure.

        atmospheric_pressure_pa:
            Ambient atmospheric pressure.

        Returns
        -------
        TorqueState
        """

        rpm = max(
            MIN_RPM,
            min(
                MAX_RPM,
                rpm
            )
        )

        omega = (
            self.rpm_to_omega(rpm)
        )

        # ----------------------------------------------------
        # 1. Combustion output
        # ----------------------------------------------------

        imep = max(
            0.0,
            combustion_state.imep_pa
        )

        indicated_power = max(
            0.0,
            combustion_state.indicated_power_w
        )

        # ----------------------------------------------------
        # 2. Mechanical losses
        # ----------------------------------------------------

        fmep = (
            self.calculate_fmep(
                rpm
            )
        )

        pumping_mep = (
            self.calculate_pumping_mep(
                rpm,
                manifold_pressure_pa,
                atmospheric_pressure_pa,
            )
        )

        # ----------------------------------------------------
        # 3. Brake MEP
        # ----------------------------------------------------

        bmep = (
            self.calculate_bmep(
                imep,
                fmep,
                pumping_mep,
            )
        )

        # ----------------------------------------------------
        # 4. Torque
        # ----------------------------------------------------

        indicated_torque = (
            self.calculate_torque_from_mep(
                imep
            )
        )

        brake_torque = (
            self.calculate_torque_from_mep(
                bmep
            )
        )

        # ----------------------------------------------------
        # 5. Brake power
        # ----------------------------------------------------

        brake_power = (
            self.calculate_power(
                brake_torque,
                omega
            )
        )

        # ----------------------------------------------------
        # 6. Mechanical efficiency
        # ----------------------------------------------------

        if indicated_power > 1.0:

            mechanical_efficiency = (
                brake_power
                / indicated_power
            )

        else:

            mechanical_efficiency = 0.0

        mechanical_efficiency = max(
            0.0,
            min(
                1.0,
                mechanical_efficiency
            )
        )

        return TorqueState(

            rpm=rpm,

            omega_rads=omega,

            imep_pa=imep,

            fmep_pa=fmep,

            pumping_mep_pa=pumping_mep,

            bmep_pa=bmep,

            indicated_power_w=(
                indicated_power
            ),

            brake_power_w=(
                brake_power
            ),

            indicated_torque_nm=(
                indicated_torque
            ),

            brake_torque_nm=(
                brake_torque
            ),

            mechanical_efficiency=(
                mechanical_efficiency
            ),
        )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    from engine.atmosphere import ISAAtmosphere
    from engine.intake import EngineIntakeModel
    from engine.combustion import EngineCombustionModel

    # --------------------------------------------------------
    # Create models
    # --------------------------------------------------------

    atmosphere_model = ISAAtmosphere()

    intake_model = EngineIntakeModel()

    combustion_model = (
        EngineCombustionModel()
    )

    torque_model = (
        EngineTorqueModel()
    )

    # --------------------------------------------------------
    # Environment
    # --------------------------------------------------------

    atmosphere = (
        atmosphere_model.calculate(
            altitude_m=3000.0
        )
    )

    # --------------------------------------------------------
    # Intake
    # --------------------------------------------------------

    intake = (
        intake_model.calculate(

            throttle_pct=80.0,

            rpm=4000.0,

            atmosphere=atmosphere,
        )
    )

    # --------------------------------------------------------
    # Combustion
    # --------------------------------------------------------

    combustion = (
        combustion_model.calculate(

            intake_state=intake,

            rpm=4000.0,
        )
    )

    # --------------------------------------------------------
    # Mechanical output
    # --------------------------------------------------------

    torque = (
        torque_model.calculate(

            combustion_state=combustion,

            rpm=4000.0,

            manifold_pressure_pa=(
                intake.manifold_pressure_pa
            ),

            atmospheric_pressure_pa=(
                atmosphere.pressure_pa
            ),
        )
    )

    # ========================================================
    # DISPLAY
    # ========================================================

    print("\nAERIS-TWIN TORQUE MODEL")
    print("=" * 80)

    print(
        f"RPM: "
        f"{torque.rpm:.0f}"
    )

    print(
        f"Angular velocity: "
        f"{torque.omega_rads:.2f} rad/s"
    )

    print(
        f"IMEP: "
        f"{torque.imep_pa / 1000:.2f} kPa"
    )

    print(
        f"FMEP: "
        f"{torque.fmep_pa / 1000:.2f} kPa"
    )

    print(
        f"Pumping MEP: "
        f"{torque.pumping_mep_pa / 1000:.2f} kPa"
    )

    print(
        f"BMEP: "
        f"{torque.bmep_pa / 1000:.2f} kPa"
    )

    print(
        f"Indicated torque: "
        f"{torque.indicated_torque_nm:.2f} Nm"
    )

    print(
        f"Brake torque: "
        f"{torque.brake_torque_nm:.2f} Nm"
    )

    print(
        f"Indicated power: "
        f"{torque.indicated_power_w / 1000:.2f} kW"
    )

    print(
        f"Brake power: "
        f"{torque.brake_power_w / 1000:.2f} kW"
    )

    print(
        f"Mechanical efficiency: "
        f"{torque.mechanical_efficiency * 100:.1f}%"
    )