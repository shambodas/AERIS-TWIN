"""
AERIS-TWIN
Engine Electrical System Model

Purpose
-------
Model the engine/aircraft electrical subsystem:

    - Alternator / generator output
    - Electrical load
    - Battery charging
    - Battery discharge
    - Bus voltage
    - Battery state of charge
    - Electrical health

Main dependency:

    Engine RPM
        ↓
    Alternator output
        ↓
    Electrical bus
        ↓
    Load + Battery

Model type
----------
Reduced-order engineering electrical model.

This module is intended for:
    - Digital Twin simulation
    - Telemetry generation
    - Fault detection
    - ML dataset generation

It is NOT an electromagnetic machine model.
"""


from dataclasses import dataclass


# ============================================================
# CONSTANTS
# ============================================================

# Nominal aircraft electrical system voltage
NOMINAL_BUS_VOLTAGE = 24.0

# Battery capacity
BATTERY_CAPACITY_AH = 20.0

# Battery energy approximation
BATTERY_ENERGY_WH = (
    NOMINAL_BUS_VOLTAGE
    * BATTERY_CAPACITY_AH
)

# Maximum alternator electrical output
MAX_ALTERNATOR_POWER_W = 600.0

# RPM at which alternator reaches rated output
ALTERNATOR_RATED_RPM = 3000.0

# Minimum RPM at which meaningful generation occurs
ALTERNATOR_CUT_IN_RPM = 1000.0

# Nominal aircraft electrical load
BASE_ELECTRICAL_LOAD_W = 250.0

# Battery limits
MIN_SOC = 0.0
MAX_SOC = 1.0

# Voltage limits
MIN_BUS_VOLTAGE = 18.0
MAX_BUS_VOLTAGE = 28.0


# ============================================================
# DATA STRUCTURE
# ============================================================

@dataclass
class ElectricalState:
    """
    Current electrical-system state.
    """

    rpm: float

    alternator_power_w: float

    electrical_load_w: float

    battery_power_w: float

    battery_current_a: float

    battery_soc: float

    bus_voltage_v: float

    alternator_available: bool

    low_voltage_warning: bool

    electrical_health: float


# ============================================================
# ELECTRICAL MODEL
# ============================================================

class EngineElectricalModel:
    """
    Reduced-order electrical subsystem.

    Sign convention for battery power:

        positive  -> battery charging
        negative  -> battery discharging
    """

    def __init__(
        self,
        battery_capacity_ah: float = BATTERY_CAPACITY_AH,
        initial_soc: float = 1.0,
    ):

        if battery_capacity_ah <= 0:

            raise ValueError(
                "Battery capacity must be positive."
            )

        self.battery_capacity_ah = (
            battery_capacity_ah
        )

        self.battery_soc = max(
            MIN_SOC,
            min(MAX_SOC, initial_soc)
        )


    # ========================================================
    # ALTERNATOR OUTPUT
    # ========================================================

    @staticmethod
    def calculate_alternator_power(
        rpm: float,
    ) -> float:
        """
        Calculate available alternator electrical power.

        The alternator output increases with engine RPM until
        its rated output is reached.

        Below cut-in speed:
            approximately zero generation.

        Above rated RPM:
            output is limited to rated power.
        """

        rpm = max(
            0.0,
            rpm
        )

        if rpm < ALTERNATOR_CUT_IN_RPM:

            return 0.0

        rpm_fraction = (
            (
                rpm
                - ALTERNATOR_CUT_IN_RPM
            )
            / (
                ALTERNATOR_RATED_RPM
                - ALTERNATOR_CUT_IN_RPM
            )
        )

        rpm_fraction = max(
            0.0,
            min(1.0, rpm_fraction)
        )

        # Smooth ramp rather than a hard linear transition.
        generation_factor = (
            rpm_fraction ** 0.70
        )

        return (
            MAX_ALTERNATOR_POWER_W
            * generation_factor
        )


    # ========================================================
    # ELECTRICAL LOAD
    # ========================================================

    @staticmethod
    def calculate_electrical_load(
        additional_load_w: float = 0.0,
    ) -> float:
        """
        Calculate aircraft electrical load.

        Base load represents avionics, sensors, communication,
        navigation and control electronics.

        Additional load can be used for mission-specific
        equipment.
        """

        additional_load_w = max(
            0.0,
            additional_load_w
        )

        return (
            BASE_ELECTRICAL_LOAD_W
            + additional_load_w
        )


    # ========================================================
    # BATTERY OPEN-CIRCUIT VOLTAGE
    # ========================================================

    @staticmethod
    def calculate_battery_ocv(
        soc: float,
    ) -> float:
        """
        Estimate battery open-circuit voltage from SOC.

        This is a simplified linearized model.
        """

        soc = max(
            MIN_SOC,
            min(MAX_SOC, soc)
        )

        minimum_voltage = 21.0
        maximum_voltage = 25.2

        return (
            minimum_voltage
            + (
                maximum_voltage
                - minimum_voltage
            )
            * soc
        )


    # ========================================================
    # BATTERY CURRENT
    # ========================================================

    @staticmethod
    def calculate_battery_current(
        battery_power_w: float,
        battery_voltage_v: float,
    ) -> float:
        """
        Calculate battery current.

        Positive current:
            charging

        Negative current:
            discharging
        """

        battery_voltage_v = max(
            1.0,
            battery_voltage_v
        )

        return (
            battery_power_w
            / battery_voltage_v
        )


    # ========================================================
    # SOC UPDATE
    # ========================================================

    def update_soc(
        self,
        battery_power_w: float,
        dt: float,
    ):
        """
        Update battery state of charge.

        Coulomb/energy-equivalent approximation:

            ΔSOC =
                P * dt / battery_energy

        Charging efficiency is applied during charging.
        """

        if dt <= 0:

            raise ValueError(
                "dt must be positive."
            )

        battery_energy_wh = (
            self.battery_capacity_ah
            * NOMINAL_BUS_VOLTAGE
        )

        # Convert W × s → Wh
        energy_change_wh = (
            battery_power_w
            * dt
            / 3600.0
        )

        if battery_power_w >= 0:

            # Charging efficiency
            effective_energy = (
                energy_change_wh
                * 0.90
            )

        else:

            # Discharge losses
            effective_energy = (
                energy_change_wh
                / 0.95
            )

        self.battery_soc += (
            effective_energy
            / battery_energy_wh
        )

        self.battery_soc = max(
            MIN_SOC,
            min(
                MAX_SOC,
                self.battery_soc
            )
        )


    # ========================================================
    # BUS VOLTAGE
    # ========================================================

    @staticmethod
    def calculate_bus_voltage(
        battery_ocv_v: float,
        alternator_power_w: float,
        electrical_load_w: float,
        battery_power_w: float,
    ) -> float:
        """
        Estimate electrical bus voltage.

        A simple regulated bus approximation is used.

        The bus is normally held close to nominal voltage when
        alternator capacity exceeds electrical demand.

        During alternator deficit, voltage falls according to
        battery loading.
        """

        net_generation = (
            alternator_power_w
            - electrical_load_w
        )

        if net_generation >= 0:

            # Alternator/regulator maintains bus voltage.
            voltage = (
                24.0
                + 0.4
                * min(
                    1.0,
                    net_generation
                    / MAX_ALTERNATOR_POWER_W
                )
            )

        else:

            # Battery supplies deficit.
            deficit_fraction = min(
                1.0,
                abs(net_generation)
                / max(
                    1.0,
                    electrical_load_w
                )
            )

            voltage = (
                battery_ocv_v
                - 2.0
                * deficit_fraction
            )

        return max(
            MIN_BUS_VOLTAGE,
            min(
                MAX_BUS_VOLTAGE,
                voltage
            )
        )


    # ========================================================
    # ELECTRICAL HEALTH
    # ========================================================

    @staticmethod
    def calculate_electrical_health(
        alternator_available: bool,
        bus_voltage_v: float,
        battery_soc: float,
    ) -> float:
        """
        Calculate a simple electrical health score.

        This is an engineering diagnostic metric, not the ML
        health score.

        Returns:
            0.0 – 1.0
        """

        health = 1.0

        # Alternator unavailable
        if not alternator_available:

            health -= 0.25

        # Low bus voltage
        if bus_voltage_v < 22.0:

            voltage_penalty = (
                (22.0 - bus_voltage_v)
                / 4.0
            )

            health -= (
                0.40
                * voltage_penalty
            )

        # Low battery SOC
        if battery_soc < 0.30:

            soc_penalty = (
                (0.30 - battery_soc)
                / 0.30
            )

            health -= (
                0.35
                * soc_penalty
            )

        return max(
            0.0,
            min(1.0, health)
        )


    # ========================================================
    # MAIN CALCULATION
    # ========================================================

    def calculate(
        self,
        rpm: float,
        dt: float,
        additional_load_w: float = 0.0,
    ) -> ElectricalState:
        """
        Calculate and update electrical subsystem.

        Parameters
        ----------
        rpm:
            Engine RPM.

        dt:
            Simulation timestep [s].

        additional_load_w:
            Additional mission electrical load.

        Returns
        -------
        ElectricalState
        """

        if dt <= 0:

            raise ValueError(
                "dt must be positive."
            )

        rpm = max(
            0.0,
            rpm
        )

        # ----------------------------------------------------
        # Alternator
        # ----------------------------------------------------

        alternator_power = (
            self.calculate_alternator_power(
                rpm
            )
        )

        alternator_available = (
            rpm
            >= ALTERNATOR_CUT_IN_RPM
        )

        # ----------------------------------------------------
        # Electrical load
        # ----------------------------------------------------

        electrical_load = (
            self.calculate_electrical_load(
                additional_load_w
            )
        )

        # ----------------------------------------------------
        # Battery power
        # ----------------------------------------------------

        battery_power = (
            alternator_power
            - electrical_load
        )

        # ----------------------------------------------------
        # Battery voltage
        # ----------------------------------------------------

        battery_ocv = (
            self.calculate_battery_ocv(
                self.battery_soc
            )
        )

        bus_voltage = (
            self.calculate_bus_voltage(

                battery_ocv_v=battery_ocv,

                alternator_power_w=(
                    alternator_power
                ),

                electrical_load_w=(
                    electrical_load
                ),

                battery_power_w=(
                    battery_power
                ),
            )
        )

        # ----------------------------------------------------
        # Battery current
        # ----------------------------------------------------

        battery_current = (
            self.calculate_battery_current(

                battery_power_w=(
                    battery_power
                ),

                battery_voltage_v=(
                    bus_voltage
                ),
            )
        )

        # ----------------------------------------------------
        # SOC
        # ----------------------------------------------------

        self.update_soc(
            battery_power_w=battery_power,
            dt=dt,
        )

        # ----------------------------------------------------
        # Electrical health
        # ----------------------------------------------------

        electrical_health = (
            self.calculate_electrical_health(

                alternator_available=(
                    alternator_available
                ),

                bus_voltage_v=(
                    bus_voltage
                ),

                battery_soc=(
                    self.battery_soc
                ),
            )
        )

        low_voltage_warning = (
            bus_voltage < 22.0
        )

        return ElectricalState(

            rpm=rpm,

            alternator_power_w=(
                alternator_power
            ),

            electrical_load_w=(
                electrical_load
            ),

            battery_power_w=(
                battery_power
            ),

            battery_current_a=(
                battery_current
            ),

            battery_soc=(
                self.battery_soc
            ),

            bus_voltage_v=(
                bus_voltage
            ),

            alternator_available=(
                alternator_available
            ),

            low_voltage_warning=(
                low_voltage_warning
            ),

            electrical_health=(
                electrical_health
            ),
        )


    # ========================================================
    # RESET
    # ========================================================

    def reset(
        self,
        initial_soc: float = 1.0,
    ):
        """
        Reset battery state.
        """

        self.battery_soc = max(
            MIN_SOC,
            min(
                MAX_SOC,
                initial_soc
            )
        )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    electrical_model = (
        EngineElectricalModel(
            initial_soc=0.80
        )
    )

    print(
        "\nAERIS-TWIN ELECTRICAL MODEL"
    )

    print(
        "=" * 90
    )

    # --------------------------------------------------------
    # Operating points
    # --------------------------------------------------------

    operating_points = [

        (
            "Engine OFF",
            0.0,
        ),

        (
            "Low RPM",
            1500.0,
        ),

        (
            "Cruise",
            3500.0,
        ),

        (
            "High RPM",
            5000.0,
        ),
    ]

    for name, rpm in operating_points:

        state = (
            electrical_model.calculate(

                rpm=rpm,

                dt=1.0,
            )
        )

        print(
            f"\n{name}"
        )

        print(
            f"RPM: "
            f"{state.rpm:.0f}"
        )

        print(
            f"Alternator: "
            f"{state.alternator_power_w:.1f} W"
        )

        print(
            f"Electrical load: "
            f"{state.electrical_load_w:.1f} W"
        )

        print(
            f"Battery power: "
            f"{state.battery_power_w:.1f} W"
        )

        print(
            f"Battery current: "
            f"{state.battery_current_a:.2f} A"
        )

        print(
            f"Battery SOC: "
            f"{state.battery_soc * 100:.2f}%"
        )

        print(
            f"Bus voltage: "
            f"{state.bus_voltage_v:.2f} V"
        )

        print(
            f"Electrical health: "
            f"{state.electrical_health * 100:.1f}%"
        )

        print(
            f"Low-voltage warning: "
            f"{state.low_voltage_warning}"
        )