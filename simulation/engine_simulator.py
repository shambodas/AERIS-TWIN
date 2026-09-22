"""
AERIS-TWIN
Integrated Virtual Engine Simulator

Purpose
-------
Integrate all engine subsystems into one time-stepped
Digital Twin simulation.

Architecture
------------

    Mission Inputs
         |
         v
    Atmosphere
         |
         v
      Intake
         |
         v
     Combustion
         |
         v
       Torque
         |
         +--------------------+
         |                    |
         v                    v
    Propeller Load       Thermal System
         |                    |
         v                    v
      RPM Dynamics       Lubrication
                              |
                              v
                         Electrical
                              |
                              v
                         Vibration
                              |
                              v
                      TRUE ENGINE STATE
                              |
                              v
                        Sensor Model
                              |
                              v
                       OBSERVED STATE

Faults
------
Fault models modify the appropriate subsystem rather than
directly corrupting the complete engine state.

Primary project fault classes:

    0 = NORMAL
    1 = MISFIRE
    2 = COOLING_DEGRADATION
    3 = COMBUSTION_INSTABILITY
    4 = SENSOR_DRIFT

This simulator is a reduced-order, physics-inspired Digital
Twin intended for:

    - SIH prototype
    - real-time simulation
    - synthetic telemetry generation
    - fault-data generation
    - ML development

It is NOT a certified flight-dynamics or engine-control model.
"""


from dataclasses import dataclass, asdict
import math


# ============================================================
# ENGINE IMPORTS
# ============================================================

from engine.atmosphere import ISAAtmosphere
from engine.intake import EngineIntakeModel
from engine.combustion import EngineCombustionModel
from engine.torque import EngineTorqueModel
from engine.propeller import FixedPitchPropellerModel
from engine.thermal import EngineThermalModel
from engine.lubrication import EngineLubricationModel
from engine.electrical import EngineElectricalModel
from engine.vibration import EngineVibrationModel
from engine.timing import InjectionTimingModel


# ============================================================
# FAULT IMPORTS
# ============================================================

from faults.misfire import MisfireModel
from faults.cooling import CoolingFaultModel
from faults.combustion_instability import CombustionInstabilityModel
from faults.excessive_vibration import ExcessiveVibrationModel
from faults.lubrication import LubricationFaultModel
from faults.sensor_faults import SensorFaultModel
from faults.injector_abnormality import InjectorAbnormalityModel


# ============================================================
# SENSOR IMPORT
# ============================================================

from sensors.sensor_model import (
    SensorModel,
    sensor_state_to_dict,
)


# ============================================================
# CONSTANTS
# ============================================================

DEFAULT_RPM = 3000.0

MIN_RPM = 800.0

MAX_RPM = 6000.0

ENGINE_INERTIA_KGM2 = 0.45

MECHANICAL_FRICTION_COEFFICIENT = 0.003

ACCESSORY_TORQUE_NM = 2.0


# ============================================================
# SIMULATION INPUT
# ============================================================

@dataclass
class EngineInputs:
    """
    External operating conditions supplied to the virtual
    engine.
    """

    altitude_m: float = 0.0

    airspeed_mps: float = 40.0

    throttle_pct: float = 70.0

    mission_load_w: float = 250.0

    ground_load_torque_nm: float = 0.0

    mission_phase: str | None = None

    # Ambient temperature offset from ISA standard (K).
    # Positive = hotter than standard day (hot-weather ops).
    temperature_offset_k: float = 0.0


# ============================================================
# TRUE ENGINE STATE
# ============================================================

@dataclass
class EngineState:
    """
    Complete physical state of the virtual engine.

    These values represent the Digital Twin's internal truth
    before sensor noise and sensor faults are applied.
    """

    time_s: float

    rpm: float

    altitude_m: float

    airspeed_mps: float

    throttle_pct: float

    air_density_kg_m3: float

    ambient_temperature_c: float

    manifold_pressure_kpa: float

    intake_temperature_c: float

    fuel_flow_kg_s: float

    torque_nm: float

    power_kw: float

    propeller_torque_nm: float

    propeller_power_kw: float

    thrust_n: float

    cht_c: list

    egt_c: list

    oil_temperature_c: float

    oil_pressure_psi: float

    oil_flow_l_min: float

    battery_voltage_v: float

    battery_current_a: float

    battery_soc: float

    vibration_rms: float

    vibration_peak: float

    vibration_0_5x: float

    vibration_1x: float

    vibration_2x: float

    #: Alternator power output [W] — from EngineElectricalModel
    alternator_power_w: float

    #: Nominal injection timing [degrees BTDC] — simulation prototype constants
    injection_timing_nominal_deg: float

    #: Actual injection timing including fault effects [degrees BTDC]
    injection_timing_actual_deg: float

    #: Timing deviation from nominal [degrees] — negative = retarded
    injection_timing_deviation_deg: float

    fault_type: str

    fault_severity: float

    fault_label: int


# ============================================================
# ENGINE SIMULATOR
# ============================================================

class EngineSimulator:
    """
    Integrated AERIS-TWIN engine Digital Twin.

    The simulator maintains the engine's physical state and
    advances it using a fixed timestep.

    The simulator does not directly generate ML labels from
    sensor observations. Labels come from the known injected
    fault scenario.
    """

    def __init__(
        self,
        num_cylinders: int = 4,
        timestep_s: float = 0.01,
        random_seed: int | None = 42,
        wear_rate_multiplier: float = 0.0,
    ):

        if num_cylinders <= 0:
            raise ValueError(
                "num_cylinders must be positive."
            )

        if timestep_s <= 0:
            raise ValueError(
                "timestep_s must be positive."
            )

        self.num_cylinders = num_cylinders

        self.dt = timestep_s

        self.time_s = 0.0

        # ----------------------------------------------------
        # Engine operating state
        # ----------------------------------------------------

        self.rpm = DEFAULT_RPM

        self.wear_index = 0.0
        
        self.wear_rate_multiplier = wear_rate_multiplier
        
        self.failed = False
        
        self.eol_timestamp = None
        
        self.eol_threshold = 1.0

        # ----------------------------------------------------
        # Physics models
        # ----------------------------------------------------

        self.atmosphere = ISAAtmosphere()

        self.intake = EngineIntakeModel()

        self.combustion = EngineCombustionModel()

        self.torque = EngineTorqueModel()

        self.propeller = (
            FixedPitchPropellerModel()
        )

        self.thermal = (
            EngineThermalModel(
                num_cylinders=num_cylinders
            )
        )

        self.lubrication = (
            EngineLubricationModel()
        )

        self.electrical = (
            EngineElectricalModel()
        )

        self.vibration = (
            EngineVibrationModel()
        )

        self.timing = (
            InjectionTimingModel()
        )

        # ----------------------------------------------------
        # Fault models
        # ----------------------------------------------------

        self.misfire = (
            MisfireModel(
                num_cylinders=num_cylinders
            )
        )

        self.cooling_fault = (
            CoolingFaultModel()
        )

        self.combustion_instability = (
            CombustionInstabilityModel()
        )

        self.excessive_vibration = (
            ExcessiveVibrationModel()
        )

        self.lubrication_fault = (
            LubricationFaultModel()
        )

        self.sensor_fault = (
            SensorFaultModel()
        )

        self.injector_abnormality = (
            InjectorAbnormalityModel()
        )

        # ----------------------------------------------------
        # Sensor observation layer
        # ----------------------------------------------------

        self.sensors = SensorModel(
            random_seed=random_seed
        )

        # ----------------------------------------------------
        # Last state
        # ----------------------------------------------------

        self.last_true_state = None

        self.last_sensor_state = None


    # ========================================================
    # FAULT MANAGEMENT
    # ========================================================

    def clear_faults(self):
        """
        Clear every currently active fault.
        """

        self.misfire.clear()

        self.cooling_fault.clear()

        self.combustion_instability.clear()
        self.excessive_vibration.clear()
        self.lubrication_fault.clear()

        self.sensor_fault.clear()

        self.injector_abnormality.clear()


    # ========================================================
    # MISFIRE
    # ========================================================

    def activate_misfire(
        self,
        severity: float = 0.8,
        cylinder: int = 3,
    ):
        """
        Activate cylinder-specific misfire.
        """

        self.clear_faults()

        self.misfire.activate(
            severity=severity,
            target_cylinder=cylinder,
        )


    # ========================================================
    # COOLING FAULT
    # ========================================================

    def activate_cooling_fault(
        self,
        severity: float = 0.7,
    ):
        """
        Activate cooling-system degradation.
        """

        self.clear_faults()

        self.cooling_fault.activate(
            severity=severity
        )


    # ========================================================
    # COMBUSTION INSTABILITY
    # ========================================================

    def activate_combustion_instability(
        self,
        severity: float = 0.7,
    ):
        """
        Activate combustion instability.
        """

        self.clear_faults()

        self.combustion_instability.activate(
            severity=severity
        )


    # ========================================================
    # EXCESSIVE VIBRATION
    # ========================================================

    def activate_vibration_fault(
        self,
        severity: float = 0.7,
    ):
        """
        Inject abnormal vibration.
        """

        self.clear_faults()
        self.excessive_vibration.activate(
            severity=severity
        )


    # ========================================================
    # INJECTOR ABNORMALITY
    # ========================================================

    def activate_injector_fault(
        self,
        severity: float = 0.7,
    ):
        """
        Inject an injector abnormality.
        """

        self.clear_faults()
        self.injector_abnormality.activate(
            severity=severity
        )

    # ========================================================
    # LUBRICATION
    # ========================================================

    def activate_lubrication_fault(
        self,
        severity: float = 0.7,
    ):
        """
        Activate lubrication degradation.
        """

        self.clear_faults()

        self.lubrication_fault.activate(
            severity=severity
        )


    # ========================================================
    # SENSOR DRIFT
    # ========================================================

    def activate_sensor_drift(
        self,
        sensor_name: str = "CHT_CYLINDER_3",
        drift_value: float = 15.0,
        severity: float = 0.7,
    ):
        """
        Activate sensor drift.

        Important:
        This does NOT modify engine physics.
        """

        self.clear_faults()

        self.sensor_fault.activate_drift(

            target_sensor=sensor_name,

            drift_value=drift_value,

            severity=severity,
        )


    # ========================================================
    # ACTIVE FAULT
    # ========================================================

    def get_active_fault(
        self,
    ) -> tuple[str, float, int]:
        """
        Return:

            fault_type
            severity
            ML label
        """

        if self.misfire.is_active():

            return (
                "MISFIRE",
                self.misfire.fault.severity,
                1,
            )

        if self.cooling_fault.is_active():

            return (
                "COOLING_DEGRADATION",
                self.cooling_fault.fault.severity,
                2,
            )

        if (
            self.combustion_instability
            .is_active()
        ):

            return (
                "COMBUSTION_INSTABILITY",
                self.combustion_instability
                .fault
                .severity,
                3,
            )

        if self.excessive_vibration.is_active():

            return (
                "EXCESSIVE_VIBRATION",
                self.excessive_vibration
                .fault
                .severity,
                6,
            )

        if self.lubrication_fault.is_active():

            return (
                "OIL_PRESSURE_DEGRADATION",
                self.lubrication_fault.fault.severity,
                5,
            )

        if self.sensor_fault.is_active():

            return (
                "SENSOR_DRIFT",
                self.sensor_fault
                .fault
                .severity,
                4,
            )

        if self.injector_abnormality.is_active():
            
            return (
                "INJECTOR_ABNORMALITY",
                self.injector_abnormality
                .fault
                .severity,
                7,
            )

        return (
            "NORMAL",
            0.0,
            0,
        )


    # ========================================================
    # FAULT DICTIONARY
    # ========================================================

    def get_physical_fault_state(
        self,
    ) -> dict | None:
        """
        Return the fault dictionary expected by the existing
        physics modules.

        SENSOR_DRIFT is deliberately excluded because it is
        not a physical engine fault.
        """

        if self.misfire.is_active():

            return (
                self.misfire.get_effect()
            )

        if self.cooling_fault.is_active():

            return (
                self.cooling_fault.get_effect()
            )

        if (
            self.combustion_instability
            .is_active()
        ):

            return (
                self.combustion_instability
                .get_effect()
            )

        if self.excessive_vibration.is_active():

            return (
                self.excessive_vibration.get_effect()
            )

        if self.lubrication_fault.is_active():

            return (
                self.lubrication_fault.get_effect()
            )
            
        if self.injector_abnormality.is_active():

            return (
                self.injector_abnormality.get_effect()
            )

        return None


    # ========================================================
    # SENSOR FAULT DICTIONARY
    # ========================================================

    def get_sensor_fault_state(
        self,
    ) -> dict | None:
        """
        Return sensor fault information.
        """

        if self.sensor_fault.is_active():

            return (
                self.sensor_fault.get_effect()
            )

        return None


    # ========================================================
    # ENGINE DYNAMICS
    # ========================================================

    def update_rpm(
        self,
        engine_torque_nm: float,
        propeller_torque_nm: float,
        ground_load_torque_nm: float = 0.0,
    ):
        """
        Update engine RPM using rotational dynamics.

            J × dω/dt = T_engine - T_load

        where:

            J = effective engine rotational inertia
            ω = angular velocity
        """

        omega = (
            self.rpm
            * 2.0
            * math.pi
            / 60.0
        )

        # ----------------------------------------------------
        # Friction
        # ----------------------------------------------------

        friction_torque = (
            MECHANICAL_FRICTION_COEFFICIENT
            * max(
                0.0,
                omega
            )
        )

        # ----------------------------------------------------
        # Total resisting torque
        # ----------------------------------------------------

        total_resisting_torque = (
            propeller_torque_nm
            + friction_torque
            + ACCESSORY_TORQUE_NM
            + max(0.0, ground_load_torque_nm)
        )

        # ----------------------------------------------------
        # Net torque
        # ----------------------------------------------------

        net_torque = (
            engine_torque_nm
            - total_resisting_torque
        )

        # ----------------------------------------------------
        # Angular acceleration
        # ----------------------------------------------------

        angular_acceleration = (
            net_torque
            / ENGINE_INERTIA_KGM2
        )

        # ----------------------------------------------------
        # Integrate
        # ----------------------------------------------------

        omega += (
            angular_acceleration
            * self.dt
        )

        new_rpm = (
            omega
            * 60.0
            / (2.0 * math.pi)
        )

        self.rpm = max(
            MIN_RPM,
            min(
                MAX_RPM,
                new_rpm
            )
        )


    # ========================================================
    # TRUE ENGINE STATE
    # ========================================================

    def build_true_state(
        self,
        inputs: EngineInputs,
        atmosphere_state,
        intake_state,
        combustion_state,
        propeller_state,
        thermal_state,
        lubrication_state,
        electrical_state,
        vibration_state,
        timing_state,
    ) -> EngineState:
        """
        Combine subsystem outputs into one physical engine
        state.
        """

        fault_type, severity, label = (
            self.get_active_fault()
        )

        # ----------------------------------------------------
        # Torque / power
        # ----------------------------------------------------

        torque_nm = float(
            getattr(
                combustion_state,
                "brake_torque_nm",
                getattr(
                    combustion_state,
                    "torque_nm",
                    0.0
                )
            )
        )

        # If torque.py provides the value, prefer it.
        if self.last_torque_state is not None:

            torque_nm = float(
                getattr(
                    self.last_torque_state,
                    "brake_torque_nm",
                    getattr(
                        self.last_torque_state,
                        "torque_nm",
                        torque_nm
                    )
                )
            )

        power_kw = (
            torque_nm
            * self.rpm
            * 2.0
            * math.pi
            / 60.0
            / 1000.0
        )

        # ----------------------------------------------------
        # Intake values
        # ----------------------------------------------------

        manifold_pressure = float(
            getattr(
                intake_state,
                "manifold_pressure_pa",
                0.0
            )
        ) / 1000.0  # Convert Pa to kPa

        intake_temperature = float(
            getattr(
                intake_state,
                "intake_temperature_c",
                getattr(
                    intake_state,
                    "temperature_c",
                    0.0
                )
            )
        )

        fuel_flow = float(
            getattr(
                combustion_state,
                "fuel_mass_flow_kg_s",
                0.0
            )
        )

        return EngineState(

            time_s=self.time_s,

            rpm=self.rpm,

            altitude_m=inputs.altitude_m,

            airspeed_mps=inputs.airspeed_mps,

            throttle_pct=inputs.throttle_pct,

            air_density_kg_m3=(
                atmosphere_state
                .density_kg_m3
            ),

            ambient_temperature_c=(
                atmosphere_state
                .temperature_c
            ),

            manifold_pressure_kpa=(
                manifold_pressure
            ),

            intake_temperature_c=(
                intake_temperature
            ),

            fuel_flow_kg_s=(
                fuel_flow
            ),

            torque_nm=(
                torque_nm
            ),

            power_kw=(
                power_kw
            ),

            propeller_torque_nm=(
                propeller_state
                .propeller_torque_nm
            ),

            propeller_power_kw=(
                propeller_state
                .propeller_power_w
                / 1000.0
            ),

            thrust_n=(
                propeller_state
                .estimated_thrust_n
            ),

            cht_c=(
                thermal_state.cht_c
            ),

            egt_c=(
                thermal_state.egt_c
            ),

            oil_temperature_c=(
                thermal_state.oil_temp_c
            ),

            oil_pressure_psi=(
                lubrication_state
                .oil_pressure_psi
            ),

            oil_flow_l_min=(
                lubrication_state
                .estimated_oil_flow_l_min
            ),

            battery_voltage_v=(
                electrical_state
                .bus_voltage_v
            ),

            battery_current_a=(
                electrical_state
                .battery_current_a
            ),

            battery_soc=(
                electrical_state
                .battery_soc
            ),

            vibration_rms=(
                vibration_state
                .signal_rms
            ),

            vibration_peak=(
                vibration_state
                .signal_peak
            ),

            vibration_0_5x=(
                vibration_state
                .order_0_5x
            ),

            vibration_1x=(
                vibration_state
                .order_1x
            ),

            vibration_2x=(
                vibration_state
                .order_2x
            ),

            alternator_power_w=(
                electrical_state
                .alternator_power_w
            ),

            injection_timing_nominal_deg=(
                timing_state
                .injection_timing_nominal_deg
            ),

            injection_timing_actual_deg=(
                timing_state
                .injection_timing_actual_deg
            ),

            injection_timing_deviation_deg=(
                timing_state
                .injection_timing_deviation_deg
            ),

            fault_type=fault_type,

            fault_severity=severity,

            fault_label=label,
        )


    # ========================================================
    # ONE SIMULATION STEP
    # ========================================================

    def step(
        self,
        inputs: EngineInputs,
    ):
        """
        Advance the complete Digital Twin by one timestep.

        Returns
        -------
        tuple
            true_state,
            sensor_state
        """

        # ====================================================
        # 1. ATMOSPHERE
        # ====================================================

        atmosphere_state = (
            self.atmosphere.calculate(
                altitude_m=inputs.altitude_m,
                temperature_offset_k=inputs.temperature_offset_k,
            )
        )

        # ====================================================
        # 2. PHYSICAL FAULT
        # ====================================================

        physical_fault = (
            self.get_physical_fault_state()
        )

        # ====================================================
        # 3. INTAKE
        # ====================================================

        intake_state = (
            self.intake.calculate(

                throttle_pct=(
                    inputs.throttle_pct
                ),

                rpm=self.rpm,

                atmosphere=(
                    atmosphere_state
                ),
            )
        )

        # ====================================================
        # 4. COMBUSTION
        # ====================================================

        combustion_fault = (
            physical_fault
        )

        combustion_state = (
            self.combustion.calculate(

                intake_state=intake_state,

                rpm=self.rpm,

                fault_state=(
                    combustion_fault
                ),
            )
        )

        # ====================================================
        # 5. TORQUE
        # ====================================================

        torque_state = self.torque.calculate(
            combustion_state=combustion_state,
            rpm=self.rpm,
            manifold_pressure_pa=(
                intake_state.manifold_pressure_pa
            ),
            atmospheric_pressure_pa=(
                atmosphere_state.pressure_pa
            ),
        )

        # Store for use in RPM dynamics
        self.last_torque_state = torque_state

        # ====================================================
        # 6. PROPELLER
        # ====================================================

        propeller_state = (
            self.propeller.calculate(

                rpm=self.rpm,

                forward_velocity_mps=(
                    inputs.airspeed_mps
                ),

                atmosphere=(
                    atmosphere_state
                ),
            )
        )

        # ====================================================
        # 7. ENGINE RPM DYNAMICS
        # ====================================================

        mission_load_torque_nm = max(0.0, float(inputs.mission_load_w)) / max(
            self.rpm * 2.0 * math.pi / 60.0,
            1.0,
        )

        engine_torque = float(
            getattr(
                self.last_torque_state,
                "brake_torque_nm",
                getattr(
                    self.last_torque_state,
                    "torque_nm",
                    0.0
                )
            )
        )

        self.update_rpm(

            engine_torque_nm=(
                engine_torque
            ),

            propeller_torque_nm=(
                propeller_state
                .propeller_torque_nm
            ),

            ground_load_torque_nm=(
                inputs.ground_load_torque_nm
                + mission_load_torque_nm
            ),
        )

        # ====================================================
        # 8. THERMAL
        # ====================================================

        thermal_state = (
            self.thermal.update(

                dt=self.dt,

                rpm=self.rpm,

                atmosphere=(
                    atmosphere_state
                ),

                intake_state=(
                    intake_state
                ),

                combustion_state=(
                    combustion_state
                ),

                fault_state=(
                    physical_fault
                ),
            )
        )

        # ====================================================
        # 9. LUBRICATION
        # ====================================================

        if not self.failed and self.wear_rate_multiplier > 0.0:
            rpm_factor = max(0.0, self.rpm / 4000.0)
            thermal_factor = max(1.0, thermal_state.cht_c[0] / 150.0)
            
            # Physics-linked quadratic wear equation based on calibration
            base_wear = 0.0001 * (rpm_factor ** 2) * (thermal_factor ** 2) * self.dt
            wear_increment = base_wear * self.wear_rate_multiplier
            
            if wear_increment > 0.0:
                self.wear_index += wear_increment
                
            if self.wear_index >= self.eol_threshold:
                self.failed = True
                self.eol_timestamp = self.time_s

        lubrication_state = (
            self.lubrication.calculate(

                rpm=self.rpm,

                oil_temperature_c=(
                    thermal_state
                    .oil_temp_c
                ),

                wear_index=self.wear_index,

                fault_state=(
                    physical_fault
                ),
            )
        )

        # ====================================================
        # 10. ELECTRICAL
        # ====================================================

        electrical_state = (
            self.electrical.calculate(

                rpm=self.rpm,

                dt=self.dt,

                additional_load_w=(
                    inputs.mission_load_w
                ),
            )
        )

        # ====================================================
        # 11. VIBRATION
        # ====================================================

        vibration_state = (
            self.vibration.calculate(

                rpm=self.rpm,

                wear_index=self.wear_index,

                fault_state=(
                    physical_fault
                ),
            )
        )

        # ====================================================
        # 11.5. INJECTION TIMING
        # ====================================================

        timing_state = (
            self.timing.calculate(

                rpm=self.rpm,

                throttle_pct=(
                    inputs.throttle_pct
                ),

                fault_state=(
                    physical_fault
                ),
            )
        )

        # ====================================================
        # 12. TRUE ENGINE STATE
        # ====================================================

        if self.failed:
            true_state = EngineState(
                time_s=self.time_s,
                rpm=0.0,
                altitude_m=inputs.altitude_m,
                airspeed_mps=inputs.airspeed_mps,
                throttle_pct=inputs.throttle_pct,
                air_density_kg_m3=atmosphere_state.density_kg_m3,
                ambient_temperature_c=atmosphere_state.temperature_c,
                manifold_pressure_kpa=0.0,
                intake_temperature_c=atmosphere_state.temperature_c,
                fuel_flow_kg_s=0.0,
                torque_nm=0.0,
                power_kw=0.0,
                propeller_torque_nm=0.0,
                propeller_power_kw=0.0,
                thrust_n=0.0,
                cht_c=[atmosphere_state.temperature_c] * self.num_cylinders,
                egt_c=[atmosphere_state.temperature_c] * self.num_cylinders,
                oil_temperature_c=atmosphere_state.temperature_c,
                oil_pressure_psi=0.0,
                oil_flow_l_min=0.0,
                battery_voltage_v=electrical_state.bus_voltage_v,
                battery_current_a=0.0,
                battery_soc=electrical_state.battery_soc,
                vibration_rms=0.0,
                vibration_peak=0.0,
                vibration_0_5x=0.0,
                vibration_1x=0.0,
                vibration_2x=0.0,
                alternator_power_w=electrical_state.alternator_power_w,
                injection_timing_nominal_deg=0.0,
                injection_timing_actual_deg=0.0,
                injection_timing_deviation_deg=0.0,
                fault_type="ENGINE_FAILURE",
                fault_severity=1.0,
                fault_label=-1,
            )
            self.rpm = 0.0
        else:
            true_state = (
                self.build_true_state(
    
                    inputs=inputs,
    
                    atmosphere_state=(
                        atmosphere_state
                    ),
    
                    intake_state=(
                        intake_state
                    ),
    
                    combustion_state=(
                        combustion_state
                    ),
    
                    propeller_state=(
                        propeller_state
                    ),
    
                    thermal_state=(
                        thermal_state
                    ),
    
                    lubrication_state=(
                        lubrication_state
                    ),
    
                    electrical_state=(
                        electrical_state
                    ),
    
                    vibration_state=(
                        vibration_state
                    ),

                    timing_state=(
                        timing_state
                    ),
                )
            )

        # ====================================================
        # 13. CONVERT TRUE STATE → SENSOR INPUT
        # ====================================================

        sensor_input = {

            "rpm":
                true_state.rpm,

            "manifold_pressure_kpa":
                true_state.manifold_pressure_kpa,

            "intake_temperature_c":
                true_state.intake_temperature_c,

            "fuel_flow_kg_s":
                true_state.fuel_flow_kg_s,

            "torque_nm":
                true_state.torque_nm,

            "power_kw":
                true_state.power_kw,

            "cht_c":
                true_state.cht_c,

            "egt_c":
                true_state.egt_c,

            "oil_temperature_c":
                true_state.oil_temperature_c,

            "oil_pressure_psi":
                true_state.oil_pressure_psi,

            "oil_flow_l_min":
                true_state.oil_flow_l_min,

            "battery_voltage_v":
                true_state.battery_voltage_v,

            "battery_current_a":
                true_state.battery_current_a,

            "battery_soc":
                true_state.battery_soc,

            "vibration_rms":
                true_state.vibration_rms,

            "vibration_peak":
                true_state.vibration_peak,

            "vibration_0_5x":
                true_state.vibration_0_5x,

            "vibration_1x":
                true_state.vibration_1x,


            "vibration_2x":
                true_state.vibration_2x,

            "alternator_power_w":
                true_state.alternator_power_w,

            "injection_timing_nominal_deg":
                true_state.injection_timing_nominal_deg,

            "injection_timing_actual_deg":
                true_state.injection_timing_actual_deg,

            "injection_timing_deviation_deg":
                true_state.injection_timing_deviation_deg,
        }

        # ====================================================
        # 14. SENSOR OBSERVATION
        # ====================================================

        sensor_state = (
            self.sensors.measure_engine(

                true_state=sensor_input,

                sensor_fault=(
                    self.get_sensor_fault_state()
                ),
            )
        )

        # ====================================================
        # 15. UPDATE TIME
        # ====================================================

        self.time_s += self.dt

        self.last_true_state = (
            true_state
        )

        self.last_sensor_state = (
            sensor_state
        )

        return (
            true_state,
            sensor_state,
        )


    # ========================================================
    # RUN SIMULATION
    # ========================================================

    def run(
        self,
        duration_s: float,
        inputs: EngineInputs,
    ):
        """
        Run the simulator for duration_s seconds.

        Returns:
            List of dictionaries containing true and observed
            engine data.
        """

        if duration_s <= 0:

            raise ValueError(
                "duration_s must be positive."
            )

        number_of_steps = int(
            duration_s
            / self.dt
        )

        results = []

        for _ in range(
            number_of_steps
        ):

            true_state, sensor_state = (
                self.step(inputs)
            )

            true_dict = asdict(
                true_state
            )

            sensor_dict = (
                sensor_state_to_dict(
                    sensor_state
                )
            )

            record = {

                "time_s":
                    true_state.time_s,

                "fault_type":
                    true_state.fault_type,

                "fault_severity":
                    true_state.fault_severity,

                "fault_label":
                    true_state.fault_label,

            }

            # ------------------------------------------------
            # Prefix physical values
            # ------------------------------------------------

            for key, value in (
                true_dict.items()
            ):

                if key in {
                    "time_s",
                    "fault_type",
                    "fault_severity",
                    "fault_label",
                }:

                    continue

                record[
                    f"true_{key}"
                ] = value

            # ------------------------------------------------
            # Prefix sensor values
            # ------------------------------------------------

            for key, value in (
                sensor_dict.items()
            ):

                record[
                    f"measured_{key}"
                ] = value

            results.append(
                record
            )

        return results


    # ========================================================
    # RESET
    # ========================================================

    def reset(
        self,
        initial_rpm: float = DEFAULT_RPM,
    ):
        """
        Reset the complete Digital Twin.
        """

        self.time_s = 0.0

        self.wear_index = 0.0
        
        self.failed = False
        
        self.eol_timestamp = None

        self.rpm = max(
            MIN_RPM,
            min(
                MAX_RPM,
                initial_rpm
            )
        )

        self.thermal.reset()

        self.electrical.reset()

        self.clear_faults()

        self.last_true_state = None

        self.last_sensor_state = None

        self.last_torque_state = None


# ============================================================
# DEMONSTRATION
# ============================================================

if __name__ == "__main__":

    print(
        "\n"
        + "=" * 80
    )

    print(
        "AERIS-TWIN INTEGRATED ENGINE SIMULATOR"
    )

    print(
        "=" * 80
    )

    # --------------------------------------------------------
    # Create simulator
    # --------------------------------------------------------

    simulator = EngineSimulator(

        num_cylinders=4,

        timestep_s=0.01,

        random_seed=42,
    )

    # --------------------------------------------------------
    # Mission / operating condition
    # --------------------------------------------------------

    inputs = EngineInputs(

        altitude_m=3000.0,

        airspeed_mps=40.0,

        throttle_pct=75.0,

        mission_load_w=300.0,
    )

    # --------------------------------------------------------
    # NORMAL
    # --------------------------------------------------------

    print(
        "\n[1] NORMAL OPERATION"
    )

    normal_results = (
        simulator.run(

            duration_s=2.0,

            inputs=inputs,
        )
    )

    normal = (
        normal_results[-1]
    )

    print(
        f"RPM: "
        f"{normal['true_rpm']:.1f}"
    )

    print(
        f"CHT C1: "
        f"{normal['true_cht_c'][0]:.1f} °C"
    )

    print(
        f"Oil temperature: "
        f"{normal['true_oil_temperature_c']:.1f} °C"
    )

    print(
        f"Oil pressure: "
        f"{normal['true_oil_pressure_psi']:.1f} psi"
    )

    print(
        f"Vibration RMS: "
        f"{normal['true_vibration_rms']:.4f}"
    )

    print(
        f"Fault: "
        f"{normal['fault_type']}"
    )

    # --------------------------------------------------------
    # MISFIRE
    # --------------------------------------------------------

    simulator.reset()

    simulator.activate_misfire(

        severity=0.85,

        cylinder=3,
    )

    print(
        "\n[2] MISFIRE"
    )

    misfire_results = (
        simulator.run(

            duration_s=2.0,

            inputs=inputs,
        )
    )

    misfire = (
        misfire_results[-1]
    )

    print(
        f"RPM: "
        f"{misfire['true_rpm']:.1f}"
    )

    print(
        f"CHT C3: "
        f"{misfire['true_cht_c'][2]:.1f} °C"
    )

    print(
        f"Vibration 0.5X: "
        f"{misfire['true_vibration_0_5x']:.4f}"
    )

    print(
        f"Fault: "
        f"{misfire['fault_type']}"
    )

    print(
        f"ML label: "
        f"{misfire['fault_label']}"
    )

    # --------------------------------------------------------
    # COOLING
    # --------------------------------------------------------

    simulator.reset()

    simulator.activate_cooling_fault(
        severity=0.80
    )

    print(
        "\n[3] COOLING DEGRADATION"
    )

    cooling_results = (
        simulator.run(

            duration_s=2.0,

            inputs=inputs,
        )
    )

    cooling = (
        cooling_results[-1]
    )

    print(
        f"CHT C1: "
        f"{cooling['true_cht_c'][0]:.1f} °C"
    )

    print(
        f"EGT C1: "
        f"{cooling['true_egt_c'][0]:.1f} °C"
    )

    print(
        f"Oil temperature: "
        f"{cooling['true_oil_temperature_c']:.1f} °C"
    )

    print(
        f"Fault: "
        f"{cooling['fault_type']}"
    )

    print(
        f"ML label: "
        f"{cooling['fault_label']}"
    )

    # --------------------------------------------------------
    # COMBUSTION INSTABILITY
    # --------------------------------------------------------

    simulator.reset()

    simulator.activate_combustion_instability(
        severity=0.80
    )

    print(
        "\n[4] COMBUSTION INSTABILITY"
    )

    instability_results = (
        simulator.run(

            duration_s=2.0,

            inputs=inputs,
        )
    )

    instability = (
        instability_results[-1]
    )

    print(
        f"Vibration RMS: "
        f"{instability['true_vibration_rms']:.4f}"
    )

    print(
        f"Vibration 2X: "
        f"{instability['true_vibration_2x']:.4f}"
    )

    print(
        f"Fault: "
        f"{instability['fault_type']}"
    )

    print(
        f"ML label: "
        f"{instability['fault_label']}"
    )

    # --------------------------------------------------------
    # SENSOR DRIFT
    # --------------------------------------------------------

    simulator.reset()

    simulator.activate_sensor_drift(

        sensor_name="CHT_CYLINDER_3",

        drift_value=15.0,

        severity=0.80,
    )

    print(
        "\n[5] SENSOR DRIFT"
    )

    sensor_results = (
        simulator.run(

            duration_s=2.0,

            inputs=inputs,
        )
    )

    sensor = (
        sensor_results[-1]
    )

    print(
        f"True CHT C3: "
        f"{sensor['true_cht_c'][2]:.2f} °C"
    )

    print(
        f"Measured CHT C3: "
        f"{sensor['measured_cht_cylinder_3_c']:.2f} °C"
    )

    print(
        f"Fault: "
        f"{sensor['fault_type']}"
    )

    print(
        f"ML label: "
        f"{sensor['fault_label']}"
    )

    print(
        "\n"
        + "=" * 80
    )

    print(
        "SIMULATION COMPLETE"
    )

    print(
        "=" * 80
    )
