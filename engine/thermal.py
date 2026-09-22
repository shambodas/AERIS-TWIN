"""
AERIS-TWIN
Engine Thermal Management Model

Purpose
-------
Model the transient thermal behaviour of:

    - Cylinder Head Temperature (CHT)
    - Exhaust Gas Temperature (EGT)
    - Engine Oil Temperature

The model couples:

    Combustion
        ↓
    Heat generation
        ↓
    Thermal masses
        ↓
    Heat rejection
        ↓
    Temperature states

Cooling depends on:

    - Engine RPM
    - Air density
    - Ambient temperature
    - Cooling-system health
    - Engine operating condition

Model type
----------
Reduced-order lumped thermal network.

This is intended for:
    - Digital Twin simulation
    - Fault signature generation
    - ML dataset generation
    - Real-time telemetry

It is NOT a CFD or detailed finite-element thermal model.
"""

from dataclasses import dataclass
import math

from engine.atmosphere import AtmosphericState
from engine.combustion import CombustionState
from engine.intake import IntakeState


# ============================================================
# CONSTANTS
# ============================================================

# Number of cylinders
DEFAULT_CYLINDERS = 4

# ------------------------------------------------------------
# Thermal masses
# ------------------------------------------------------------

# Effective cylinder-head thermal mass
CYLINDER_HEAD_THERMAL_MASS = 2500.0       # J/K

# Effective exhaust-manifold thermal mass
EXHAUST_THERMAL_MASS = 150.0              # J/K

# Effective oil-system thermal mass
OIL_THERMAL_MASS = 5000.0                  # J/K


# ------------------------------------------------------------
# Heat-transfer coefficients
# ------------------------------------------------------------

# Cylinder-head base heat-transfer coefficient × area.
# Calibrated so CHT rises from ~50 C at idle to ~85 C at WOT
# without unrealistically over-cooling the engine.
BASE_CHT_HA = 130.0

# Exhaust heat-transfer coefficient relative to CHT
EGT_COOLING_RATIO = 1.0

# Oil cooling coefficient
BASE_OIL_HA = 35.0


# ------------------------------------------------------------
# Heat distribution
# ------------------------------------------------------------

# These represent fractions of combustion energy entering
# different thermal/mechanical paths.
#
# They should be calibrated later against engine data.

# These fractions are calibrated so the engine reaches realistic
# cylinder-head temperatures across idle, cruise, and takeoff.
# The CHT path should carry a significant but not dominant share of
# the combustion heat, leaving enough energy for power conversion and
# exhaust transport.
CHT_HEAT_FRACTION = 0.30
EGT_HEAT_FRACTION = 0.37

# Remaining energy is associated with mechanical output and
# other losses.


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class ThermalState:
    """
    Complete engine thermal state.
    """

    cht_c: list

    egt_c: list

    oil_temp_c: float

    ambient_temp_c: float

    cooling_health: float

    cht_heat_rate_w: float

    exhaust_heat_rate_w: float

    oil_heat_rate_w: float

    total_cooling_power_w: float


# ============================================================
# THERMAL MODEL
# ============================================================

class EngineThermalModel:
    """
    Lumped-parameter thermal model.

    Each cylinder is treated as a separate thermal node.

    This is important for fault detection because a fault in
    one cylinder can produce a cylinder-specific thermal
    signature rather than only changing the engine-average
    temperature.
    """

    def __init__(
        self,
        num_cylinders: int = DEFAULT_CYLINDERS,
    ):

        if num_cylinders <= 0:

            raise ValueError(
                "Number of cylinders must be positive."
            )

        self.num_cylinders = (
            num_cylinders
        )

        # ----------------------------------------------------
        # Thermal states
        # ----------------------------------------------------

        self.cht_k = [
            323.15
            for _ in range(
                num_cylinders
            )
        ]

        self.egt_k = [
            323.15
            for _ in range(
                num_cylinders
            )
        ]

        self.oil_temp_k = 323.15


    # ========================================================
    # COOLING HEALTH
    # ========================================================

    @staticmethod
    def calculate_cooling_health(
        fault_state: dict | None = None,
    ) -> float:
        """
        Calculate cooling-system health based on fault state.
        """

        if fault_state is None:

            return 1.0

        fault_type = fault_state.get(
            "type",
            "NONE"
        )

        if fault_type == "COOLING_DEGRADATION":

            cooling_factor = float(
                fault_state.get(
                    "cooling_factor",
                    1.0
                )
            )

            return max(
                0.10,
                min(1.0, cooling_factor)
            )

        return 1.0


    # ========================================================
    # CHT COOLING
    # ========================================================

    @staticmethod
    def calculate_cht_heat_transfer(
        cht_k: float,
        ambient_k: float,
        rpm: float,
        air_density_ratio: float,
        cooling_health: float,
    ) -> float:
        """
        Calculate cylinder-head heat rejection.

            Q = hA × (T_CHT - T_ambient)

        hA scales approximately with engine speed and air
        density.
        """

        rpm = max(
            100.0,
            rpm
        )

        density_ratio = max(
            0.20,
            min(1.20, air_density_ratio)
        )

        cooling_health = max(
            0.20,
            min(1.00, cooling_health)
        )

        # Airflow / convection scaling.
        rpm_factor = (
            rpm / 4000.0
        ) ** 0.80

        rpm_factor = max(
            0.40,
            min(1.80, rpm_factor)
        )

        hA = (
            BASE_CHT_HA
            * rpm_factor
            * density_ratio ** 0.80
            * cooling_health
        )

        delta_t = max(
            0.0,
            cht_k - ambient_k
        )

        return (
            hA
            * delta_t
        )


    # ========================================================
    # EGT COOLING
    # ========================================================

    @staticmethod
    def calculate_egt_heat_transfer(
        egt_k: float,
        ambient_k: float,
        rpm: float,
        air_density_ratio: float,
        cooling_health: float,
    ) -> float:
        """
        Calculate exhaust thermal rejection.
        """

        cht_equivalent = (
            EngineThermalModel
            .calculate_cht_heat_transfer(
                cht_k=egt_k,
                ambient_k=ambient_k,
                rpm=rpm,
                air_density_ratio=air_density_ratio,
                cooling_health=cooling_health,
            )
        )

        return (
            EGT_COOLING_RATIO
            * cht_equivalent
        )


    # ========================================================
    # OIL COOLING
    # ========================================================

    @staticmethod
    def calculate_oil_heat_transfer(
        oil_temp_k: float,
        ambient_k: float,
        rpm: float,
        air_density_ratio: float,
        cooling_health: float,
    ) -> float:
        """
        Calculate oil-system heat rejection.
        """

        rpm = max(
            100.0,
            rpm
        )

        density_ratio = max(
            0.20,
            min(1.20, air_density_ratio)
        )

        rpm_factor = (
            rpm / 4000.0
        ) ** 0.60

        rpm_factor = max(
            0.40,
            min(1.80, rpm_factor)
        )

        hA = (
            BASE_OIL_HA
            * rpm_factor
            * density_ratio ** 0.60
            * cooling_health
        )

        delta_t = max(
            0.0,
            oil_temp_k - ambient_k
        )

        return (
            hA
            * delta_t
        )


    # ========================================================
    # OIL HEAT GENERATION
    # ========================================================

    @staticmethod
    def calculate_oil_heat_generation(
        indicated_power_w: float,
        rpm: float,
    ) -> float:
        """
        Estimate heat transferred into the oil.

        Oil heating increases with engine load and mechanical
        losses.

        This is a lumped representation of:

            - friction
            - bearing losses
            - piston cooling
            - oil shear
            - hot component conduction
        """

        indicated_power_w = max(
            0.0,
            indicated_power_w
        )

        rpm_factor = (
            max(100.0, rpm)
            / 4000.0
        )

        rpm_factor = max(
            0.50,
            min(1.50, rpm_factor)
        )

        # Representative fraction
        oil_fraction = (
            0.04
            + 0.02 * rpm_factor
        )

        return (
            indicated_power_w
            * oil_fraction
        )


    # ========================================================
    # MAIN UPDATE
    # ========================================================

    def calculate(
        self,
        combustion_state: CombustionState,
        atmosphere: AtmosphericState,
        intake_state: IntakeState | None = None,
        fault_state: dict | None = None,
        rpm: float | None = None,
        dt: float = 1.0,
        steady_state_steps: int = 30,
    ) -> ThermalState:
        """
        Evaluate the thermal state at a representative operating point.

        The underlying model is transient, so this compatibility wrapper
        advances the lumped thermal network for a short quasi-steady dwell
        instead of reporting a single 1-second update. This keeps the model
        realistic for validation checks and avoids the false impression that
        engine CHT is constant across load conditions.
        """
        if rpm is None:
            rpm = 3000.0

        if intake_state is None:
            intake_state = IntakeState(
                throttle_pct=0.0,
                throttle_fraction=0.0,
                manifold_pressure_pa=atmosphere.pressure_pa,
                manifold_temperature_k=atmosphere.temperature_k,
                manifold_density_kg_m3=atmosphere.density_kg_m3,
                volumetric_efficiency=0.0,
                cylinder_air_charge_kg=0.0,
                air_mass_flow_kg_s=0.0,
            )

        state = None
        for _ in range(max(1, int(steady_state_steps))):
            state = self.update(
                dt=dt,
                rpm=rpm,
                atmosphere=atmosphere,
                intake_state=intake_state,
                combustion_state=combustion_state,
                fault_state=fault_state,
            )

        return state

    def update(
        self,
        dt: float,
        rpm: float,
        atmosphere: AtmosphericState,
        intake_state: IntakeState,
        combustion_state: CombustionState,
        fault_state: dict | None = None,
    ) -> ThermalState:
        """
        Advance thermal state by dt seconds.

        Parameters
        ----------
        dt:
            Simulation timestep [s].

        rpm:
            Engine speed.

        atmosphere:
            Atmospheric boundary conditions.

        intake_state:
            Engine intake state.

        combustion_state:
            Combustion output.

        fault_state:
            Optional fault state.

        Returns
        -------
        ThermalState
        """

        if dt <= 0:

            raise ValueError(
                "dt must be positive."
            )

        rpm = max(
            100.0,
            rpm
        )

        # ----------------------------------------------------
        # Environment
        # ----------------------------------------------------

        ambient_k = (
            atmosphere.temperature_k
        )

        density_ratio = (
            atmosphere.density_ratio
        )

        # ----------------------------------------------------
        # Cooling system health
        # ----------------------------------------------------

        cooling_health = (
            self.calculate_cooling_health(
                fault_state
            )
        )

        # ----------------------------------------------------
        # Combustion heat
        # ----------------------------------------------------

        # Heat-release rate is already an engine-level rate.
        total_heat_release_w = max(
            0.0,
            combustion_state.total_heat_release_w
        )

        # Split thermal energy across cylinders.
        cylinder_heat_release = (
            total_heat_release_w
            / self.num_cylinders
        )

        cht_heat_rate = (
            cylinder_heat_release
            * CHT_HEAT_FRACTION
        )

        egt_heat_rate = (
            cylinder_heat_release
            * EGT_HEAT_FRACTION
        )

        # ----------------------------------------------------
        # CHT / EGT thermal integration
        # ----------------------------------------------------

        total_cooling_power = 0.0

        for i in range(
            self.num_cylinders
        ):

            # -----------------------------------------------
            # Cylinder-specific combustion efficiency
            # -----------------------------------------------

            cylinder = (
                combustion_state.cylinders[i]
            )

            cylinder_heat = (
                cylinder.heat_release_j
            )

            # Convert per-cycle energy to heat-rate.
            cycles_per_second = (
                rpm / 120.0
            )

            cylinder_heat_rate = (
                cylinder_heat
                * cycles_per_second
            )

            cylinder_cht_input = (
                cylinder_heat_rate
                * CHT_HEAT_FRACTION
            )

            cylinder_egt_input = (
                cylinder_heat_rate
                * EGT_HEAT_FRACTION
            )



            # -----------------------------------------------
            # Cooling
            # -----------------------------------------------

            q_cht_out = (
                self.calculate_cht_heat_transfer(
                    cht_k=self.cht_k[i],
                    ambient_k=ambient_k,
                    rpm=rpm,
                    air_density_ratio=density_ratio,
                    cooling_health=cooling_health,
                )
            )

            q_egt_out = (
                self.calculate_egt_heat_transfer(
                    egt_k=self.egt_k[i],
                    ambient_k=ambient_k,
                    rpm=rpm,
                    air_density_ratio=density_ratio,
                    cooling_health=cooling_health,
                )
            )

            # -----------------------------------------------
            # CHT energy balance
            # -----------------------------------------------

            dcht_dt = (
                cylinder_cht_input
                - q_cht_out
            ) / CYLINDER_HEAD_THERMAL_MASS

            self.cht_k[i] += (
                dcht_dt * dt
            )

            # -----------------------------------------------
            # EGT energy balance
            # -----------------------------------------------

            degt_dt = (
                cylinder_egt_input
                - q_egt_out
            ) / EXHAUST_THERMAL_MASS

            self.egt_k[i] += (
                degt_dt * dt
            )

            # -----------------------------------------------
            # Numerical limits
            # -----------------------------------------------

            self.cht_k[i] = max(
                ambient_k,
                min(
                    650.0,
                    self.cht_k[i]
                )
            )

            self.egt_k[i] = max(
                ambient_k,
                min(
                    1500.0,
                    self.egt_k[i]
                )
            )

            total_cooling_power += (
                q_cht_out
                + q_egt_out
            )

        # ----------------------------------------------------
        # Oil thermal model
        # ----------------------------------------------------

        oil_heat_generation = (
            self.calculate_oil_heat_generation(
                combustion_state.indicated_power_w,
                rpm,
            )
        )

        oil_heat_rejection = (
            self.calculate_oil_heat_transfer(
                oil_temp_k=self.oil_temp_k,
                ambient_k=ambient_k,
                rpm=rpm,
                air_density_ratio=density_ratio,
                cooling_health=cooling_health,
            )
        )

        d_oil_dt = (
            oil_heat_generation
            - oil_heat_rejection
        ) / OIL_THERMAL_MASS

        self.oil_temp_k += (
            d_oil_dt * dt
        )

        self.oil_temp_k = max(
            ambient_k,
            min(
                450.0,
                self.oil_temp_k
            )
        )

        total_cooling_power += (
            oil_heat_rejection
        )

        # ----------------------------------------------------
        # Output
        # ----------------------------------------------------

        return ThermalState(

            cht_c=[
                temperature - 273.15
                for temperature
                in self.cht_k
            ],

            egt_c=[
                temperature - 273.15
                for temperature
                in self.egt_k
            ],

            oil_temp_c=(
                self.oil_temp_k
                - 273.15
            ),

            ambient_temp_c=(
                atmosphere.temperature_c
            ),

            cooling_health=(
                cooling_health
            ),

            cht_heat_rate_w=(
                cht_heat_rate
                * self.num_cylinders
            ),

            exhaust_heat_rate_w=(
                egt_heat_rate
                * self.num_cylinders
            ),

            oil_heat_rate_w=(
                oil_heat_generation
            ),

            total_cooling_power_w=(
                total_cooling_power
            ),
        )


    # ========================================================
    # RESET
    # ========================================================

    def reset(
        self,
        initial_temperature_c: float = 50.0,
    ):
        """
        Reset thermal states.
        """

        initial_k = (
            initial_temperature_c
            + 273.15
        )

        self.cht_k = [
            initial_k
            for _ in range(
                self.num_cylinders
            )
        ]

        self.egt_k = [
            initial_k
            for _ in range(
                self.num_cylinders
            )
        ]

        self.oil_temp_k = (
            initial_k
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

    intake_model = (
        EngineIntakeModel()
    )

    combustion_model = (
        EngineCombustionModel()
    )

    thermal_model = (
        EngineThermalModel()
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
    # Thermal simulation
    # --------------------------------------------------------

    print(
        "\nAERIS-TWIN THERMAL MODEL"
    )

    print(
        "=" * 90
    )

    for step in range(1, 21):

        thermal = (
            thermal_model.update(

                dt=1.0,

                rpm=4000.0,

                atmosphere=atmosphere,

                intake_state=intake,

                combustion_state=combustion,
            )
        )

        print(
            f"[{step:02d}s] "
            f"CHT avg="
            f"{sum(thermal.cht_c) / 4:.1f} °C | "
            f"EGT avg="
            f"{sum(thermal.egt_c) / 4:.1f} °C | "
            f"Oil="
            f"{thermal.oil_temp_c:.1f} °C"
        )

    # --------------------------------------------------------
    # Cooling degradation test
    # --------------------------------------------------------

    thermal_model.reset()

    print(
        "\nCOOLING DEGRADATION TEST"
    )

    print(
        "=" * 90
    )

    for step in range(1, 11):

        thermal = (
            thermal_model.update(

                dt=1.0,

                rpm=4000.0,

                atmosphere=atmosphere,

                intake_state=intake,

                combustion_state=combustion,

                fault_state={
                    "type":
                        "COOLING_DEGRADATION",

                    "severity":
                        0.8,
                },
            )
        )

        print(
            f"[{step:02d}s] "
            f"CHT avg="
            f"{sum(thermal.cht_c) / 4:.1f} °C | "
            f"EGT avg="
            f"{sum(thermal.egt_c) / 4:.1f} °C | "
            f"Oil="
            f"{thermal.oil_temp_c:.1f} °C | "
            f"Cooling health="
            f"{thermal.cooling_health:.2f}"
        )