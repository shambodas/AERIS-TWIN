"""
AERIS-TWIN
Engine Combustion Model

Purpose
-------
Convert intake air charge into:

    Air mass flow
        ↓
    Fuel mass flow
        ↓
    AFR / equivalence ratio
        ↓
    Combustion efficiency
        ↓
    Heat release
        ↓
    IMEP

Model type
----------
Mean-value / reduced-order thermodynamic combustion model.

Important:
    This is an engineering simulation model for the AERIS-TWIN
    Digital Twin and ML data-generation pipeline. It is not a
    cycle-resolved CFD or certified engine combustion model.
"""

from dataclasses import dataclass
import math
import random

from engine.intake import IntakeState


# ============================================================
# CONSTANTS
# ============================================================

# Representative gasoline / aviation gasoline properties
STOICH_AFR = 14.7

FUEL_LHV_J_KG = 44.0e6

# Representative combustion efficiency
BASE_COMBUSTION_EFFICIENCY = 0.95

# Four-stroke engine
FOUR_STROKE = 4.0

# Representative engine displacement (1.211 liters / 1211 cc)
ENGINE_DISPLACEMENT_M3 = 0.001211

# Reference pressure used for normalized load calculations
REFERENCE_PRESSURE_PA = 101325.0

# Representative pumping-loss contribution
BASE_PUMPING_MEP_PA = 20_000.0

# Bounds for numerical stability
MIN_IMEP_PA = 0.0
MAX_IMEP_PA = 1.2e6


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class CylinderCombustionState:
    """
    Combustion state of one cylinder.
    """

    cylinder_id: int

    air_mass_kg: float

    fuel_mass_kg: float

    afr: float

    equivalence_ratio: float

    combustion_efficiency: float

    heat_release_j: float

    indicated_work_j: float

    imep_pa: float


@dataclass
class CombustionState:
    """
    Complete engine combustion state.
    """

    air_mass_flow_kg_s: float

    fuel_mass_flow_kg_s: float

    afr: float

    equivalence_ratio: float

    combustion_efficiency: float

    total_heat_release_w: float

    indicated_power_w: float

    imep_pa: float

    cylinders: list


# ============================================================
# COMBUSTION MODEL
# ============================================================

class EngineCombustionModel:
    """
    Mean-value combustion model for a four-cylinder,
    four-stroke piston engine.
    """

    def __init__(
        self,
        num_cylinders: int = 4,
        displacement_m3: float = ENGINE_DISPLACEMENT_M3,
        stoich_afr: float = STOICH_AFR,
        fuel_lhv_j_kg: float = FUEL_LHV_J_KG,
    ):

        if num_cylinders <= 0:
            raise ValueError(
                "Number of cylinders must be positive."
            )

        if displacement_m3 <= 0:
            raise ValueError(
                "Engine displacement must be positive."
            )

        if stoich_afr <= 0:
            raise ValueError(
                "Stoichiometric AFR must be positive."
            )

        if fuel_lhv_j_kg <= 0:
            raise ValueError(
                "Fuel LHV must be positive."
            )

        self.num_cylinders = num_cylinders

        self.displacement_m3 = displacement_m3

        self.cylinder_displacement_m3 = (
            displacement_m3 / num_cylinders
        )

        self.stoich_afr = stoich_afr

        self.fuel_lhv_j_kg = fuel_lhv_j_kg

        self.base_efficiency = (
            BASE_COMBUSTION_EFFICIENCY
        )


    # ========================================================
    # FUEL FLOW
    # ========================================================

    def calculate_fuel_flow(
        self,
        air_mass_flow_kg_s: float,
        target_afr: float | None = None,
    ) -> float:
        """
        Calculate fuel mass flow.

            mdot_fuel = mdot_air / AFR

        If target AFR is omitted, stoichiometric AFR is used.
        """

        if air_mass_flow_kg_s < 0:
            raise ValueError(
                "Air mass flow cannot be negative."
            )

        if target_afr is None:
            target_afr = self.stoich_afr

        if target_afr <= 0:
            raise ValueError(
                "AFR must be positive."
            )

        return (
            air_mass_flow_kg_s
            / target_afr
        )


    # ========================================================
    # AIR-FUEL RATIO
    # ========================================================

    def calculate_afr(
        self,
        air_mass_flow_kg_s: float,
        fuel_mass_flow_kg_s: float,
    ) -> float:
        """
        Calculate actual air-fuel ratio.
        """

        if fuel_mass_flow_kg_s <= 0:
            return float("inf")

        return (
            air_mass_flow_kg_s
            / fuel_mass_flow_kg_s
        )


    # ========================================================
    # EQUIVALENCE RATIO
    # ========================================================

    def calculate_equivalence_ratio(
        self,
        afr: float,
    ) -> float:
        """
        Calculate equivalence ratio:

            phi = AFR_stoich / AFR_actual

        phi = 1.0  -> stoichiometric
        phi < 1.0  -> lean
        phi > 1.0  -> rich
        """

        if not math.isfinite(afr) or afr <= 0:
            return 0.0

        return (
            self.stoich_afr
            / afr
        )


    # ========================================================
    # COMBUSTION EFFICIENCY
    # ========================================================

    def calculate_base_efficiency(
        self,
        equivalence_ratio: float,
    ) -> float:
        """
        Estimate combustion efficiency as a function of
        equivalence ratio.

        Efficiency is highest near the nominal operating
        region and decreases for extremely lean/rich mixtures.

        This provides a smooth physical relationship rather
        than a binary combustion/no-combustion switch.
        """

        phi = equivalence_ratio

        if phi <= 0:
            return 0.0

        # Nominal operating point
        phi_optimum = 1.0

        # Gaussian-shaped efficiency envelope
        spread = 0.45

        mixture_factor = math.exp(
            -0.5
            * (
                (phi - phi_optimum)
                / spread
            ) ** 2
        )

        efficiency = (
            0.70
            + 0.25 * mixture_factor
        )

        return max(
            0.0,
            min(0.98, efficiency)
        )


    # ========================================================
    # CYLINDER EFFICIENCY
    # ========================================================

    def calculate_cylinder_efficiencies(
        self,
        equivalence_ratio: float,
        fault_state: dict | None = None,
    ) -> list:
        """
        Calculate combustion efficiency for every cylinder.

        fault_state is optional and can contain:

            {
                "type": "MISFIRE",
                "severity": 0.7
            }

        This keeps fault injection separate from the core
        combustion equations.
        """

        base_efficiency = (
            self.calculate_base_efficiency(
                equivalence_ratio
            )
        )

        efficiencies = [
            base_efficiency
            for _ in range(
                self.num_cylinders
            )
        ]

        if fault_state is None:
            return efficiencies

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

        # ----------------------------------------------------
        # Misfire
        # ----------------------------------------------------

        if fault_type == "MISFIRE":

            # Cylinder 3 is used as the demonstration fault
            # cylinder, consistent with the original simulator.
            fault_cylinder = 2

            efficiencies[fault_cylinder] *= (
                1.0 - severity
            )

        # ----------------------------------------------------
        # Combustion instability
        # ----------------------------------------------------

        elif fault_type == "COMBUSTION_INSTABILITY":

            variation_sigma = (
                0.10 * severity
            )

            for i in range(
                self.num_cylinders
            ):

                efficiencies[i] *= (
                    1.0
                    + random.gauss(
                        0.0,
                        variation_sigma
                    )
                )

                efficiencies[i] = max(
                    0.40,
                    min(
                        0.98,
                        efficiencies[i]
                    )
                )

        # ----------------------------------------------------
        # Injector Abnormality
        # ----------------------------------------------------
        
        elif fault_type == "INJECTOR_ABNORMALITY":
            
            fault_cylinder = 2
            k = 0.15
            efficiencies[fault_cylinder] *= (
                1.0 - k * severity
            )
            efficiencies[fault_cylinder] = max(
                0.40, 
                efficiencies[fault_cylinder]
            )

        return efficiencies


    # ========================================================
    # HEAT RELEASE
    # ========================================================

    def calculate_heat_release(
        self,
        fuel_mass_kg: float,
        combustion_efficiency: float,
    ) -> float:
        """
        Chemical energy released during combustion:

            Q = mfuel * LHV * eta_comb
        """

        fuel_mass_kg = max(
            0.0,
            fuel_mass_kg
        )

        combustion_efficiency = max(
            0.0,
            min(
                1.0,
                combustion_efficiency
            )
        )

        return (
            fuel_mass_kg
            * self.fuel_lhv_j_kg
            * combustion_efficiency
        )


    # ========================================================
    # INDICATED WORK
    # ========================================================

    def calculate_indicated_work(
        self,
        heat_release_j: float,
    ) -> float:
        """
        Convert released chemical energy into indicated work.

        A representative thermodynamic conversion efficiency
        is used here.

        The value is intentionally separate from combustion
        efficiency because:

            combustion efficiency
                !=
            indicated thermal efficiency
        """

        indicated_thermal_efficiency = 0.38

        return (
            heat_release_j
            * indicated_thermal_efficiency
        )


    # ========================================================
    # IMEP
    # ========================================================

    def calculate_imep(
        self,
        indicated_work_j: float,
        cylinder_displacement_m3: float,
    ) -> float:
        """
        Calculate indicated mean effective pressure.

            IMEP = W_indicated / V_displacement
        """

        if cylinder_displacement_m3 <= 0:
            raise ValueError(
                "Cylinder displacement must be positive."
            )

        imep = (
            indicated_work_j
            / cylinder_displacement_m3
        )

        return max(
            MIN_IMEP_PA,
            min(
                MAX_IMEP_PA,
                imep
            )
        )


    # ========================================================
    # MAIN CALCULATION
    # ========================================================

    def calculate(
        self,
        intake_state: IntakeState,
        rpm: float,
        fault_state: dict | None = None,
    ) -> CombustionState:
        """
        Calculate complete engine combustion state.

        Parameters
        ----------
        intake_state:
            Output from EngineIntakeModel.

        rpm:
            Current engine speed.

        fault_state:
            Optional fault description.

        Returns
        -------
        CombustionState
        """

        if rpm < 0:
            raise ValueError(
                "RPM cannot be negative."
            )

        air_mass_flow = max(
            0.0,
            intake_state.air_mass_flow_kg_s
        )

        # ----------------------------------------------------
        # Fuel system
        # ----------------------------------------------------

        fuel_mass_flow = (
            self.calculate_fuel_flow(
                air_mass_flow
            )
        )

        # ----------------------------------------------------
        # Overall AFR
        # ----------------------------------------------------

        afr = self.calculate_afr(
            air_mass_flow,
            fuel_mass_flow
        )

        equivalence_ratio = (
            self.calculate_equivalence_ratio(
                afr
            )
        )

        # ----------------------------------------------------
        # Cylinder distribution
        # ----------------------------------------------------

        cylinder_air_flow = (
            air_mass_flow
            / self.num_cylinders
        )

        cylinder_fuel_flow = (
            fuel_mass_flow
            / self.num_cylinders
        )

        cylinder_air_mass = (
            cylinder_air_flow
            * 120.0
            / max(rpm, 1.0)
        )

        cylinder_fuel_mass = (
            cylinder_fuel_flow
            * 120.0
            / max(rpm, 1.0)
        )

        # ----------------------------------------------------
        # Fault-modified efficiencies
        # ----------------------------------------------------

        efficiencies = (
            self.calculate_cylinder_efficiencies(
                equivalence_ratio,
                fault_state
            )
        )

        cylinders = []

        total_heat_release_per_cycle = 0.0
        total_indicated_work_per_cycle = 0.0

        # ----------------------------------------------------
        # Individual cylinders
        # ----------------------------------------------------
        
        cylinder_fuel_masses = [cylinder_fuel_mass] * self.num_cylinders
        
        if fault_state is not None and fault_state.get("type") == "INJECTOR_ABNORMALITY":
            severity = max(0.0, min(1.0, float(fault_state.get("severity", 0.0))))
            cylinder_fuel_masses[2] *= (1.0 - 0.5 * severity)
            
            # Recompute total fuel flow slightly reduced by the affected cylinder
            actual_total_mass = sum(cylinder_fuel_masses)
            fuel_mass_flow = actual_total_mass * max(rpm, 1.0) / 120.0

        for i in range(
            self.num_cylinders
        ):

            efficiency = efficiencies[i]

            heat_release = (
                self.calculate_heat_release(
                    cylinder_fuel_masses[i],
                    efficiency
                )
            )

            indicated_work = (
                self.calculate_indicated_work(
                    heat_release
                )
            )

            imep = (
                self.calculate_imep(
                    indicated_work,
                    self.cylinder_displacement_m3
                )
            )

            cylinder_state = (
                CylinderCombustionState(

                    cylinder_id=i + 1,

                    air_mass_kg=(
                        cylinder_air_mass
                    ),

                    fuel_mass_kg=(
                        cylinder_fuel_masses[i]
                    ),

                    afr=afr,

                    equivalence_ratio=(
                        equivalence_ratio
                    ),

                    combustion_efficiency=(
                        efficiency
                    ),

                    heat_release_j=(
                        heat_release
                    ),

                    indicated_work_j=(
                        indicated_work
                    ),

                    imep_pa=imep,
                )
            )

            cylinders.append(
                cylinder_state
            )

            total_heat_release_per_cycle += (
                heat_release
            )

            total_indicated_work_per_cycle += (
                indicated_work
            )

        # ----------------------------------------------------
        # Convert per-cycle work to indicated power
        #
        # Four-stroke:
        #
        # cycles/sec = RPM / 120
        # ----------------------------------------------------

        cycles_per_second = (
            rpm / 120.0
        )

        indicated_power = (
            total_indicated_work_per_cycle
            * cycles_per_second
        )

        # ----------------------------------------------------
        # Engine-average IMEP
        # ----------------------------------------------------

        engine_imep = (
            total_indicated_work_per_cycle
            / self.displacement_m3
        )

        engine_imep = max(
            MIN_IMEP_PA,
            min(
                MAX_IMEP_PA,
                engine_imep
            )
        )

        # ----------------------------------------------------
        # Heat-release rate
        # ----------------------------------------------------

        heat_release_rate = (
            total_heat_release_per_cycle
            * cycles_per_second
        )

        average_efficiency = (
            sum(efficiencies)
            / len(efficiencies)
        )

        return CombustionState(

            air_mass_flow_kg_s=(
                air_mass_flow
            ),

            fuel_mass_flow_kg_s=(
                fuel_mass_flow
            ),

            afr=afr,

            equivalence_ratio=(
                equivalence_ratio
            ),

            combustion_efficiency=(
                average_efficiency
            ),

            total_heat_release_w=(
                heat_release_rate
            ),

            indicated_power_w=(
                indicated_power
            ),

            imep_pa=(
                engine_imep
            ),

            cylinders=cylinders,
        )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    from engine.atmosphere import ISAAtmosphere
    from engine.intake import EngineIntakeModel

    # --------------------------------------------------------
    # Create models
    # --------------------------------------------------------

    atmosphere_model = ISAAtmosphere()

    intake_model = EngineIntakeModel()

    combustion_model = (
        EngineCombustionModel()
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

    intake = intake_model.calculate(

        throttle_pct=80.0,

        rpm=4000.0,

        atmosphere=atmosphere,
    )

    # --------------------------------------------------------
    # Normal combustion
    # --------------------------------------------------------

    normal = combustion_model.calculate(

        intake_state=intake,

        rpm=4000.0,
    )

    # --------------------------------------------------------
    # Misfire combustion
    # --------------------------------------------------------

    misfire = combustion_model.calculate(

        intake_state=intake,

        rpm=4000.0,

        fault_state={
            "type": "MISFIRE",
            "severity": 0.8,
        }
    )

    # ========================================================
    # DISPLAY
    # ========================================================

    print("\nAERIS-TWIN COMBUSTION MODEL")
    print("=" * 80)

    print("\nNORMAL")

    print(
        f"Air flow: "
        f"{normal.air_mass_flow_kg_s:.5f} kg/s"
    )

    print(
        f"Fuel flow: "
        f"{normal.fuel_mass_flow_kg_s:.6f} kg/s"
    )

    print(
        f"AFR: "
        f"{normal.afr:.2f}"
    )

    print(
        f"Equivalence ratio: "
        f"{normal.equivalence_ratio:.3f}"
    )

    print(
        f"Combustion efficiency: "
        f"{normal.combustion_efficiency:.3f}"
    )

    print(
        f"IMEP: "
        f"{normal.imep_pa / 1000:.2f} kPa"
    )

    print(
        f"Indicated power: "
        f"{normal.indicated_power_w / 1000:.2f} kW"
    )

    print("\nCYLINDER STATES")

    for cylinder in normal.cylinders:

        print(
            f"Cylinder {cylinder.cylinder_id}: "
            f"Efficiency="
            f"{cylinder.combustion_efficiency:.3f} | "
            f"IMEP="
            f"{cylinder.imep_pa / 1000:.2f} kPa"
        )

    print("\nMISFIRE — CYLINDER 3")

    for cylinder in misfire.cylinders:

        print(
            f"Cylinder {cylinder.cylinder_id}: "
            f"Efficiency="
            f"{cylinder.combustion_efficiency:.3f} | "
            f"IMEP="
            f"{cylinder.imep_pa / 1000:.2f} kPa"
        )