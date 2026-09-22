"""
AERIS-TWIN
Propeller Aerodynamic Load Model

Purpose
-------
Calculate aerodynamic torque and power demand imposed on
the engine by a fixed-pitch propeller.

Physical relationship
---------------------

    Advance Ratio:

        J = V / (nD)

    Propeller Torque:

        Q = Cq * rho * n^2 * D^5

    Propeller Power:

        P = Cp * rho * n^3 * D^5

where:

    J   = advance ratio
    V   = aircraft forward velocity [m/s]
    n   = propeller rotational speed [rev/s]
    D   = propeller diameter [m]
    rho = air density [kg/m^3]
    Cq  = torque coefficient
    Cp  = power coefficient

Model type
----------
Reduced-order aerodynamic propeller model suitable for
real-time Digital Twin simulation.

IMPORTANT
---------
The coefficients used here are representative approximations.
For an industry-validation model, they should eventually be
replaced by manufacturer propeller maps or experimentally
measured propeller performance data.
"""

from dataclasses import dataclass
import math

from engine.atmosphere import AtmosphericState


# ============================================================
# CONSTANTS
# ============================================================

# Representative fixed-pitch propeller diameter (55 cm for small UAV)
DEFAULT_PROP_DIAMETER_M = 0.55

# Minimum rotational speed to avoid division by zero
MIN_PROP_RPS = 1.0

# Physical upper limit for numerical protection
MAX_PROP_RPS = 120.0


# ============================================================
# DATA STRUCTURE
# ============================================================

@dataclass
class PropellerState:
    """
    Aerodynamic state of the propeller.
    """

    rpm: float

    rotational_speed_rps: float

    forward_velocity_mps: float

    air_density_kg_m3: float

    advance_ratio: float

    torque_coefficient: float

    power_coefficient: float

    thrust_coefficient: float

    propeller_torque_nm: float

    propeller_power_w: float

    estimated_thrust_n: float


# ============================================================
# PROPELLER MODEL
# ============================================================

class FixedPitchPropellerModel:
    """
    Mean-value fixed-pitch propeller model.

    The model uses nondimensional propeller coefficients as
    functions of advance ratio.

    This gives the Digital Twin a physically meaningful
    coupling between:

        altitude
        air density
        aircraft speed
        propeller RPM
        engine load
    """

    def __init__(
        self,
        diameter_m: float = DEFAULT_PROP_DIAMETER_M,
    ):

        if diameter_m <= 0:

            raise ValueError(
                "Propeller diameter must be positive."
            )

        self.diameter_m = diameter_m


    # ========================================================
    # RPM CONVERSION
    # ========================================================

    @staticmethod
    def rpm_to_rps(
        rpm: float
    ) -> float:
        """
        Convert propeller RPM to revolutions per second.
        """

        return max(
            0.0,
            rpm
        ) / 60.0


    # ========================================================
    # ADVANCE RATIO
    # ========================================================

    def calculate_advance_ratio(
        self,
        forward_velocity_mps: float,
        rotational_speed_rps: float,
    ) -> float:
        """
        Calculate propeller advance ratio.

            J = V / (nD)
        """

        forward_velocity_mps = max(
            0.0,
            forward_velocity_mps
        )

        rotational_speed_rps = max(
            MIN_PROP_RPS,
            rotational_speed_rps
        )

        advance_ratio = (
            forward_velocity_mps
            / (
                rotational_speed_rps
                * self.diameter_m
            )
        )

        return max(
            0.0,
            advance_ratio
        )


    # ========================================================
    # TORQUE COEFFICIENT
    # ========================================================

    @staticmethod
    def calculate_torque_coefficient(
        advance_ratio: float
    ) -> float:
        """
        Estimate propeller torque coefficient.

        For a fixed-pitch propeller, Cq decreases as advance
        ratio increases.

        The polynomial is a representative approximation,
        not a manufacturer propeller map.
        
        NOTE: Coefficients calibrated for 0.55m diameter small
        UAV propeller with realistic 1200cc engine.
        """

        J = max(
            0.0,
            advance_ratio
        )

        # Static torque coefficient - scaled for small UAV propeller
        # Original empirical value 50.0 was for large geometry / out of scale
        # Adjusted to produce realistic 15-30 Nm load at cruise
        cq_static = 0.213

        # Approximate reduction with advance ratio
        cq = (
            cq_static
            - 0.040 * J
            + 0.012 * J ** 2
        )

        # Keep the coefficient physically bounded.
        return max(
            0.005,
            min(0.35, cq)
        )


    # ========================================================
    # POWER COEFFICIENT
    # ========================================================

    @staticmethod
    def calculate_power_coefficient(
        torque_coefficient: float
    ) -> float:
        """
        Convert torque coefficient to power coefficient.

            Cp = 2π Cq

        because:

            P = Qω
              = Q(2πn)
        """

        return (
            2.0
            * math.pi
            * torque_coefficient
        )


    # ========================================================
    # THRUST COEFFICIENT
    # ========================================================

    @staticmethod
    def calculate_thrust_coefficient(
        advance_ratio: float
    ) -> float:
        """
        Representative thrust coefficient model.

        A fixed-pitch propeller produces maximum thrust near
        static / low-advance-ratio operation and gradually
        loses thrust as forward speed increases.
        """

        J = max(
            0.0,
            advance_ratio
        )

        ct = (
            0.11
            - 0.09 * J
            + 0.015 * J ** 2
        )

        return max(
            0.0,
            min(0.12, ct)
        )


    # ========================================================
    # PROPELLER TORQUE
    # ========================================================

    def calculate_propeller_torque(
        self,
        torque_coefficient: float,
        air_density_kg_m3: float,
        rotational_speed_rps: float,
    ) -> float:
        """
        Calculate propeller aerodynamic torque.

            Q = Cq * rho * n² * D⁵
        """

        rho = max(
            0.0,
            air_density_kg_m3
        )

        n = max(
            0.0,
            rotational_speed_rps
        )

        D = self.diameter_m

        torque = (
            torque_coefficient
            * rho
            * n ** 2
            * D ** 5
        )

        return max(
            0.0,
            torque
        )


    # ========================================================
    # PROPELLER POWER
    # ========================================================

    def calculate_propeller_power(
        self,
        torque_nm: float,
        rotational_speed_rps: float,
    ) -> float:
        """
        Calculate propeller aerodynamic power.

            P = Q * 2πn
        """

        return (
            max(0.0, torque_nm)
            * 2.0
            * math.pi
            * max(0.0, rotational_speed_rps)
        )


    # ========================================================
    # THRUST
    # ========================================================

    def calculate_thrust(
        self,
        thrust_coefficient: float,
        air_density_kg_m3: float,
        rotational_speed_rps: float,
    ) -> float:
        """
        Calculate propeller thrust.

            T = Ct * rho * n² * D⁴
        """

        rho = max(
            0.0,
            air_density_kg_m3
        )

        n = max(
            0.0,
            rotational_speed_rps
        )

        D = self.diameter_m

        thrust = (
            thrust_coefficient
            * rho
            * n ** 2
            * D ** 4
        )

        return max(
            0.0,
            thrust
        )


    # ========================================================
    # MAIN CALCULATION
    # ========================================================

    def calculate(
        self,
        rpm: float,
        forward_velocity_mps: float,
        atmosphere: AtmosphericState,
    ) -> PropellerState:
        """
        Calculate complete propeller aerodynamic state.

        Parameters
        ----------
        rpm:
            Propeller rotational speed.

        forward_velocity_mps:
            Aircraft forward velocity.

        atmosphere:
            AtmosphericState from atmosphere.py.

        Returns
        -------
        PropellerState
        """

        rpm = max(
            0.0,
            rpm
        )

        rpm = min(
            rpm,
            MAX_PROP_RPS * 60.0
        )

        forward_velocity_mps = max(
            0.0,
            forward_velocity_mps
        )

        # ----------------------------------------------------
        # Rotational speed
        # ----------------------------------------------------

        n = self.rpm_to_rps(
            rpm
        )

        # ----------------------------------------------------
        # Advance ratio
        # ----------------------------------------------------

        J = self.calculate_advance_ratio(
            forward_velocity_mps,
            n,
        )

        # ----------------------------------------------------
        # Propeller coefficients
        # ----------------------------------------------------

        cq = self.calculate_torque_coefficient(
            J
        )

        cp = self.calculate_power_coefficient(
            cq
        )

        ct = self.calculate_thrust_coefficient(
            J
        )

        # ----------------------------------------------------
        # Aerodynamic torque
        # ----------------------------------------------------

        propeller_torque = (
            self.calculate_propeller_torque(
                cq,
                atmosphere.density_kg_m3,
                n,
            )
        )

        # ----------------------------------------------------
        # Aerodynamic power
        # ----------------------------------------------------

        propeller_power = (
            self.calculate_propeller_power(
                propeller_torque,
                n,
            )
        )

        # ----------------------------------------------------
        # Thrust
        # ----------------------------------------------------

        thrust = (
            self.calculate_thrust(
                ct,
                atmosphere.density_kg_m3,
                n,
            )
        )

        return PropellerState(

            rpm=rpm,

            rotational_speed_rps=n,

            forward_velocity_mps=(
                forward_velocity_mps
            ),

            air_density_kg_m3=(
                atmosphere.density_kg_m3
            ),

            advance_ratio=J,

            torque_coefficient=cq,

            power_coefficient=cp,

            thrust_coefficient=ct,

            propeller_torque_nm=(
                propeller_torque
            ),

            propeller_power_w=(
                propeller_power
            ),

            estimated_thrust_n=(
                thrust
            ),
        )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    from engine.atmosphere import ISAAtmosphere

    # --------------------------------------------------------
    # Create models
    # --------------------------------------------------------

    atmosphere_model = ISAAtmosphere()

    propeller_model = (
        FixedPitchPropellerModel()
    )

    # --------------------------------------------------------
    # Sea-level environment
    # --------------------------------------------------------

    sea_level = (
        atmosphere_model.calculate(
            altitude_m=0.0
        )
    )

    # --------------------------------------------------------
    # High-altitude environment
    # --------------------------------------------------------

    high_altitude = (
        atmosphere_model.calculate(
            altitude_m=5000.0
        )
    )

    # --------------------------------------------------------
    # Test cases
    # --------------------------------------------------------

    test_cases = [

        (
            "Sea Level / Static",
            sea_level,
            5000.0,
            0.0,
        ),

        (
            "Sea Level / Cruise",
            sea_level,
            5000.0,
            40.0,
        ),

        (
            "High Altitude / Cruise",
            high_altitude,
            5000.0,
            40.0,
        ),
    ]

    # ========================================================
    # DISPLAY
    # ========================================================

    print(
        "\nAERIS-TWIN PROPELLER MODEL"
    )

    print(
        "=" * 90
    )

    for (
        name,
        atmosphere,
        rpm,
        velocity,
    ) in test_cases:

        state = (
            propeller_model.calculate(

                rpm=rpm,

                forward_velocity_mps=velocity,

                atmosphere=atmosphere,
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
            f"Forward velocity: "
            f"{state.forward_velocity_mps:.1f} m/s"
        )

        print(
            f"Air density: "
            f"{state.air_density_kg_m3:.3f} kg/m³"
        )

        print(
            f"Advance ratio J: "
            f"{state.advance_ratio:.3f}"
        )

        print(
            f"Cq: "
            f"{state.torque_coefficient:.4f}"
        )

        print(
            f"Cp: "
            f"{state.power_coefficient:.4f}"
        )

        print(
            f"Ct: "
            f"{state.thrust_coefficient:.4f}"
        )

        print(
            f"Propeller torque: "
            f"{state.propeller_torque_nm:.2f} Nm"
        )

        print(
            f"Propeller power: "
            f"{state.propeller_power_w / 1000:.2f} kW"
        )

        print(
            f"Estimated thrust: "
            f"{state.estimated_thrust_n:.1f} N"
        )