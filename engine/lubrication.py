"""
AERIS-TWIN
Engine Lubrication System Model

Purpose
-------
Model the engine lubrication system:

    - Oil temperature
    - Oil viscosity
    - Oil pressure
    - Oil-flow behaviour
    - Lubrication health

Inputs
------
    - Engine RPM
    - Oil temperature
    - Engine load
    - Engine wear
    - Atmospheric temperature
    - Fault state

Outputs
-------
    - Dynamic oil viscosity
    - Oil pressure
    - Estimated oil flow
    - Lubrication health
    - Oil-pressure margin

Model type
----------
Reduced-order engineering lubrication model.

This model is intended for:
    - Digital Twin simulation
    - Fault signature generation
    - ML dataset generation

It is NOT a detailed CFD lubrication model.
"""


from dataclasses import dataclass
import math


# ============================================================
# CONSTANTS
# ============================================================

# Reference oil viscosity at 100°C.
# Representative value for a piston-engine lubricant.
REFERENCE_VISCOSITY_PA_S = 0.010

REFERENCE_OIL_TEMP_C = 100.0

# Temperature-viscosity sensitivity.
VISCOSITY_TEMPERATURE_COEFFICIENT = 0.025

# Reference oil pressure.
BASE_OIL_PRESSURE_PSI = 60.0

# Reference engine speed.
REFERENCE_RPM = 4000.0

# Pressure contribution from engine speed.
RPM_PRESSURE_GAIN_PSI = 12.0

# Oil-flow coefficient.
OIL_FLOW_COEFFICIENT = 0.000055

# Minimum oil pressure considered acceptable
MIN_OPERATIONAL_PRESSURE_PSI = 25.0

# Maximum numerical oil pressure
MAX_OIL_PRESSURE_PSI = 100.0


# ============================================================
# DATA STRUCTURE
# ============================================================

@dataclass
class LubricationState:
    """
    Current lubrication-system state.
    """

    oil_temperature_c: float

    dynamic_viscosity_pa_s: float

    oil_pressure_psi: float

    estimated_oil_flow_l_min: float

    lubrication_health: float

    pressure_margin_psi: float

    pressure_ratio: float


# ============================================================
# LUBRICATION MODEL
# ============================================================

class EngineLubricationModel:
    """
    Reduced-order engine lubrication model.

    The model captures the major qualitative dependencies:

        Higher temperature
            ↓
        Lower viscosity

        Higher RPM
            ↓
        Higher pump speed / pressure

        Higher wear
            ↓
        Reduced pressure capability

        Lubrication degradation
            ↓
        Additional pressure loss
    """

    def __init__(
        self,
        base_pressure_psi: float = BASE_OIL_PRESSURE_PSI,
    ):

        if base_pressure_psi <= 0:

            raise ValueError(
                "Base oil pressure must be positive."
            )

        self.base_pressure_psi = (
            base_pressure_psi
        )


    # ========================================================
    # OIL VISCOSITY
    # ========================================================

    @staticmethod
    def calculate_viscosity(
        oil_temperature_c: float,
    ) -> float:
        """
        Estimate dynamic oil viscosity.

        Viscosity decreases with increasing temperature.

        A bounded exponential relationship is used:

            μ(T) = μ_ref *
                   exp[-k(T - T_ref)]

        Returns:
            Dynamic viscosity [Pa·s]
        """

        temperature_difference = (
            oil_temperature_c
            - REFERENCE_OIL_TEMP_C
        )

        viscosity = (
            REFERENCE_VISCOSITY_PA_S
            * math.exp(
                -VISCOSITY_TEMPERATURE_COEFFICIENT
                * temperature_difference
            )
        )

        return max(
            0.001,
            min(0.10, viscosity)
        )


    # ========================================================
    # LUBRICATION HEALTH
    # ========================================================

    @staticmethod
    def calculate_lubrication_health(
        wear_index: float = 0.0,
        fault_state: dict | None = None,
    ) -> float:
        """
        Calculate lubrication-system health.

        Wear produces gradual degradation.

        A dedicated lubrication fault can additionally be
        introduced later.

        Health:

            1.0 = healthy
            0.0 = severely degraded
        """

        wear_index = max(
            0.0,
            min(1.0, wear_index)
        )

        health = (
            1.0
            - 0.30 * wear_index
        )

        if fault_state is not None:

            fault_type = fault_state.get(
                "type",
                "NONE"
            )

            severity = float(
                fault_state.get(
                    "severity",
                    0.0
                )
            )

            severity = max(
                0.0,
                min(1.0, severity)
            )

            if fault_type == (
                "LUBRICATION_DEGRADATION"
            ):

                health *= (
                    1.0
                    - 0.50 * severity
                )

        return max(
            0.30,
            min(1.0, health)
        )


    # ========================================================
    # OIL PRESSURE
    # ========================================================

    def calculate_oil_pressure(
        self,
        rpm: float,
        oil_temperature_c: float,
        wear_index: float = 0.0,
        fault_state: dict | None = None,
    ) -> float:
        """
        Estimate oil pressure.

        Pressure depends on:

            - RPM
            - Oil viscosity
            - Engine wear
            - Lubrication health

        The model represents the behaviour of an engine-driven
        oil pump without explicitly resolving pump geometry.
        """

        rpm = max(
            0.0,
            rpm
        )

        wear_index = max(
            0.0,
            min(1.0, wear_index)
        )

        # ----------------------------------------------------
        # RPM contribution
        # ----------------------------------------------------

        rpm_ratio = (
            rpm / REFERENCE_RPM
        )

        rpm_ratio = max(
            0.0,
            min(1.50, rpm_ratio)
        )

        rpm_pressure = (
            RPM_PRESSURE_GAIN_PSI
            * rpm_ratio
        )

        # ----------------------------------------------------
        # Viscosity effect
        # ----------------------------------------------------

        viscosity = (
            self.calculate_viscosity(
                oil_temperature_c
            )
        )

        viscosity_ratio = (
            viscosity
            / REFERENCE_VISCOSITY_PA_S
        )

        viscosity_ratio = max(
            0.50,
            min(2.0, viscosity_ratio)
        )

        # Very thick oil can increase pressure, while very thin
        # oil reduces the pressure capability.

        viscosity_factor = (
            0.75
            + 0.25 * viscosity_ratio
        )

        # ----------------------------------------------------
        # Wear effect
        # ----------------------------------------------------

        wear_loss = (
            15.0
            * wear_index
        )

        # ----------------------------------------------------
        # Lubrication health
        # ----------------------------------------------------

        health = (
            self.calculate_lubrication_health(
                wear_index,
                fault_state,
            )
        )

        health_loss = (
            20.0
            * (1.0 - health)
        )

        # ----------------------------------------------------
        # Pressure
        # ----------------------------------------------------

        pressure = (
            self.base_pressure_psi
            + rpm_pressure
        )

        pressure *= (
            viscosity_factor
        )

        pressure -= (
            wear_loss
            + health_loss
        )

        return max(
            0.0,
            min(
                MAX_OIL_PRESSURE_PSI,
                pressure
            )
        )


    # ========================================================
    # OIL FLOW
    # ========================================================

    @staticmethod
    def calculate_oil_flow(
        oil_pressure_psi: float,
        viscosity_pa_s: float,
    ) -> float:
        """
        Estimate oil flow.

        Approximation:

            Q ∝ ΔP / μ

        Higher pressure increases flow while higher viscosity
        reduces flow.

        Returns:
            Estimated oil flow [L/min].
        """

        pressure = max(
            0.0,
            oil_pressure_psi
        )

        viscosity = max(
            0.001,
            viscosity_pa_s
        )

        flow = (
            OIL_FLOW_COEFFICIENT
            * pressure
            / viscosity
        )

        return max(
            0.0,
            min(20.0, flow)
        )


    # ========================================================
    # PRESSURE MARGIN
    # ========================================================

    @staticmethod
    def calculate_pressure_margin(
        oil_pressure_psi: float,
    ) -> float:
        """
        Calculate margin above minimum operational pressure.
        """

        return (
            oil_pressure_psi
            - MIN_OPERATIONAL_PRESSURE_PSI
        )


    # ========================================================
    # MAIN CALCULATION
    # ========================================================

    def calculate(
        self,
        rpm: float,
        oil_temperature_c: float,
        wear_index: float = 0.0,
        fault_state: dict | None = None,
    ) -> LubricationState:
        """
        Calculate the complete lubrication state.
        """

        oil_temperature_c = max(
            -20.0,
            min(
                180.0,
                oil_temperature_c
            )
        )

        # ----------------------------------------------------
        # Viscosity
        # ----------------------------------------------------

        viscosity = (
            self.calculate_viscosity(
                oil_temperature_c
            )
        )

        # ----------------------------------------------------
        # Health
        # ----------------------------------------------------

        health = (
            self.calculate_lubrication_health(
                wear_index,
                fault_state,
            )
        )

        # ----------------------------------------------------
        # Oil pressure
        # ----------------------------------------------------

        oil_pressure = (
            self.calculate_oil_pressure(

                rpm=rpm,

                oil_temperature_c=(
                    oil_temperature_c
                ),

                wear_index=wear_index,

                fault_state=fault_state,
            )
        )

        # ----------------------------------------------------
        # Oil flow
        # ----------------------------------------------------

        oil_flow = (
            self.calculate_oil_flow(

                oil_pressure_psi=(
                    oil_pressure
                ),

                viscosity_pa_s=(
                    viscosity
                ),
            )
        )

        # ----------------------------------------------------
        # Pressure margin
        # ----------------------------------------------------

        pressure_margin = (
            self.calculate_pressure_margin(
                oil_pressure
            )
        )

        # ----------------------------------------------------
        # Pressure ratio
        # ----------------------------------------------------

        pressure_ratio = (
            oil_pressure
            / self.base_pressure_psi
        )

        return LubricationState(

            oil_temperature_c=(
                oil_temperature_c
            ),

            dynamic_viscosity_pa_s=(
                viscosity
            ),

            oil_pressure_psi=(
                oil_pressure
            ),

            estimated_oil_flow_l_min=(
                oil_flow
            ),

            lubrication_health=(
                health
            ),

            pressure_margin_psi=(
                pressure_margin
            ),

            pressure_ratio=(
                pressure_ratio
            ),
        )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    lubrication_model = (
        EngineLubricationModel()
    )

    print(
        "\nAERIS-TWIN LUBRICATION MODEL"
    )

    print(
        "=" * 90
    )

    # --------------------------------------------------------
    # Normal operating points
    # --------------------------------------------------------

    operating_points = [

        (
            "Cold / Low RPM",
            1500.0,
            50.0,
            0.0,
        ),

        (
            "Normal Cruise",
            4000.0,
            90.0,
            0.0,
        ),

        (
            "High Load",
            5500.0,
            110.0,
            0.0,
        ),

        (
            "Worn Engine",
            4000.0,
            110.0,
            0.70,
        ),
    ]

    for (
        name,
        rpm,
        oil_temp,
        wear,
    ) in operating_points:

        state = (
            lubrication_model.calculate(

                rpm=rpm,

                oil_temperature_c=oil_temp,

                wear_index=wear,
            )
        )

        print(
            f"\n{name}"
        )

        print(
            f"RPM: "
            f"{rpm:.0f}"
        )

        print(
            f"Oil temperature: "
            f"{state.oil_temperature_c:.1f} °C"
        )

        print(
            f"Viscosity: "
            f"{state.dynamic_viscosity_pa_s:.5f} Pa·s"
        )

        print(
            f"Oil pressure: "
            f"{state.oil_pressure_psi:.2f} psi"
        )

        print(
            f"Oil flow: "
            f"{state.estimated_oil_flow_l_min:.2f} L/min"
        )

        print(
            f"Lubrication health: "
            f"{state.lubrication_health * 100:.1f}%"
        )

        print(
            f"Pressure margin: "
            f"{state.pressure_margin_psi:.2f} psi"
        )

    # --------------------------------------------------------
    # Fault demonstration
    # --------------------------------------------------------

    print(
        "\nLUBRICATION DEGRADATION TEST"
    )

    print(
        "=" * 90
    )

    degraded = (
        lubrication_model.calculate(

            rpm=4000.0,

            oil_temperature_c=110.0,

            wear_index=0.30,

            fault_state={
                "type":
                    "LUBRICATION_DEGRADATION",

                "severity":
                    0.80,
            },
        )
    )

    print(
        f"Oil pressure: "
        f"{degraded.oil_pressure_psi:.2f} psi"
    )

    print(
        f"Oil flow: "
        f"{degraded.estimated_oil_flow_l_min:.2f} L/min"
    )

    print(
        f"Lubrication health: "
        f"{degraded.lubrication_health * 100:.1f}%"
    )

    print(
        f"Pressure margin: "
        f"{degraded.pressure_margin_psi:.2f} psi"
    )