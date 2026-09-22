"""
AERIS-TWIN
Sensor Observation Model

Purpose
-------
Convert true Digital Twin engine states into realistic sensor
measurements.

The sensor model introduces:

    - Measurement noise
    - Sensor bias
    - Sensor drift
    - Quantization
    - Physical measurement limits

IMPORTANT
---------
This module does NOT modify the true engine state.

It creates a separate observed sensor state.

Architecture:

    True Engine State
            |
            v
       Sensor Model
            |
       +----+----+
       |         |
      Noise     Fault
       |         |
       +----+----+
            |
            v
      Sensor State
            |
            v
       Telemetry / ML
"""


from dataclasses import dataclass
import random


# ============================================================
# SENSOR CONFIGURATION
# ============================================================

@dataclass(frozen=True)
class SensorConfig:
    """
    Configuration of an individual sensor.

    Parameters
    ----------
    name:
        Sensor identifier.

    noise_std:
        Standard deviation of measurement noise.

    bias:
        Constant sensor bias.

    resolution:
        Sensor quantization resolution.

    minimum:
        Minimum measurable value.

    maximum:
        Maximum measurable value.
    """

    name: str

    noise_std: float

    bias: float

    resolution: float

    minimum: float

    maximum: float


# ============================================================
# SENSOR STATE
# ============================================================

@dataclass
class SensorState:
    """
    Complete observed sensor state.

    The values in this structure represent what the aircraft
    data-acquisition system would observe, NOT the true
    internal Digital Twin state.
    """

    rpm: float

    manifold_pressure_kpa: float

    intake_temperature_c: float

    fuel_flow_kg_s: float

    torque_nm: float

    power_kw: float

    cht_cylinder_1_c: float

    cht_cylinder_2_c: float

    cht_cylinder_3_c: float

    cht_cylinder_4_c: float

    egt_cylinder_1_c: float

    egt_cylinder_2_c: float

    egt_cylinder_3_c: float

    egt_cylinder_4_c: float

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

    alternator_power_w: float

    injection_timing_nominal_deg: float

    injection_timing_actual_deg: float

    injection_timing_deviation_deg: float


# ============================================================
# SENSOR MODEL
# ============================================================

class SensorModel:
    """
    Realistic observation layer for AERIS-TWIN.

    The model applies independent sensor characteristics to
    true engine values.

    It is intentionally kept separate from engine physics.

    This allows us to distinguish:

        Physical degradation
                from
        Measurement degradation
    """

    def __init__(
        self,
        random_seed: int | None = 42,
    ):

        if random_seed is not None:

            random.seed(
                random_seed
            )

        # ----------------------------------------------------
        # Sensor definitions
        # ----------------------------------------------------

        self.sensors = {

            "RPM": SensorConfig(
                name="RPM",
                noise_std=5.0,
                bias=0.0,
                resolution=1.0,
                minimum=0.0,
                maximum=8000.0,
            ),

            "MANIFOLD_PRESSURE": SensorConfig(
                name="MANIFOLD_PRESSURE",
                noise_std=0.15,
                bias=0.0,
                resolution=0.01,
                minimum=0.0,
                maximum=150.0,
            ),

            "INTAKE_TEMPERATURE": SensorConfig(
                name="INTAKE_TEMPERATURE",
                noise_std=0.5,
                bias=0.0,
                resolution=0.1,
                minimum=-60.0,
                maximum=120.0,
            ),

            "FUEL_FLOW": SensorConfig(
                name="FUEL_FLOW",
                noise_std=0.00005,
                bias=0.0,
                resolution=0.00001,
                minimum=0.0,
                maximum=0.01,
            ),

            "TORQUE": SensorConfig(
                name="TORQUE",
                noise_std=0.5,
                bias=0.0,
                resolution=0.1,
                minimum=0.0,
                maximum=500.0,
            ),

            "POWER": SensorConfig(
                name="POWER",
                noise_std=0.05,
                bias=0.0,
                resolution=0.01,
                minimum=0.0,
                maximum=300.0,
            ),

            "CHT": SensorConfig(
                name="CHT",
                noise_std=0.8,
                bias=0.0,
                resolution=0.1,
                minimum=-40.0,
                maximum=350.0,
            ),

            "EGT": SensorConfig(
                name="EGT",
                noise_std=1.5,
                bias=0.0,
                resolution=0.1,
                minimum=-40.0,
                maximum=1200.0,
            ),

            "OIL_TEMPERATURE": SensorConfig(
                name="OIL_TEMPERATURE",
                noise_std=0.6,
                bias=0.0,
                resolution=0.1,
                minimum=-40.0,
                maximum=180.0,
            ),

            "OIL_PRESSURE": SensorConfig(
                name="OIL_PRESSURE",
                noise_std=0.5,
                bias=0.0,
                resolution=0.1,
                minimum=0.0,
                maximum=120.0,
            ),

            "OIL_FLOW": SensorConfig(
                name="OIL_FLOW",
                noise_std=0.05,
                bias=0.0,
                resolution=0.01,
                minimum=0.0,
                maximum=30.0,
            ),

            "BATTERY_VOLTAGE": SensorConfig(
                name="BATTERY_VOLTAGE",
                noise_std=0.05,
                bias=0.0,
                resolution=0.01,
                minimum=0.0,
                maximum=32.0,
            ),

            "BATTERY_CURRENT": SensorConfig(
                name="BATTERY_CURRENT",
                noise_std=0.1,
                bias=0.0,
                resolution=0.01,
                minimum=-100.0,
                maximum=100.0,
            ),

            "BATTERY_SOC": SensorConfig(
                name="BATTERY_SOC",
                noise_std=0.005,
                bias=0.0,
                resolution=0.001,
                minimum=0.0,
                maximum=1.0,
            ),

            "VIBRATION_RMS": SensorConfig(
                name="VIBRATION_RMS",
                noise_std=0.005,
                bias=0.0,
                resolution=0.001,
                minimum=0.0,
                maximum=20.0,
            ),

            "VIBRATION_PEAK": SensorConfig(
                name="VIBRATION_PEAK",
                noise_std=0.01,
                bias=0.0,
                resolution=0.001,
                minimum=0.0,
                maximum=50.0,
            ),

            "VIBRATION_0_5X": SensorConfig(
                name="VIBRATION_0_5X",
                noise_std=0.005,
                bias=0.0,
                resolution=0.001,
                minimum=0.0,
                maximum=20.0,
            ),

            "VIBRATION_1X": SensorConfig(
                name="VIBRATION_1X",
                noise_std=0.005,
                bias=0.0,
                resolution=0.001,
                minimum=0.0,
                maximum=20.0,
            ),

            "VIBRATION_2X": SensorConfig(
                name="VIBRATION_2X",
                noise_std=0.005,
                bias=0.0,
                resolution=0.001,
                minimum=0.0,
                maximum=20.0,
            ),

            "ALTERNATOR_POWER": SensorConfig(
                name="ALTERNATOR_POWER",
                noise_std=2.0,
                bias=0.0,
                resolution=1.0,
                minimum=0.0,
                maximum=1000.0,
            ),

            "INJECTION_TIMING": SensorConfig(
                name="INJECTION_TIMING",
                noise_std=0.0,
                bias=0.0,
                resolution=0.1,
                minimum=-30.0,
                maximum=50.0,
            ),
        }


    # ========================================================
    # SINGLE SENSOR MEASUREMENT
    # ========================================================

    def measure(
        self,
        sensor_name: str,
        true_value: float,
        drift_value: float = 0.0,
    ) -> float:
        """
        Convert one true physical value into a sensor reading.

        Measurement model:

            y = quantize(
                    true_value
                    + bias
                    + drift
                    + noise
                )

        The result is bounded by the sensor's physical range.
        """

        if sensor_name not in self.sensors:

            raise KeyError(
                f"Unknown sensor: "
                f"{sensor_name}"
            )

        config = (
            self.sensors[
                sensor_name
            ]
        )

        # ----------------------------------------------------
        # Random measurement noise
        # ----------------------------------------------------

        noise = random.gauss(
            0.0,
            config.noise_std
        )

        # ----------------------------------------------------
        # Raw measurement
        # ----------------------------------------------------

        measured_value = (
            true_value
            + config.bias
            + drift_value
            + noise
        )

        # ----------------------------------------------------
        # Sensor range
        # ----------------------------------------------------

        measured_value = max(
            config.minimum,
            min(
                config.maximum,
                measured_value
            )
        )

        # ----------------------------------------------------
        # Quantization
        # ----------------------------------------------------

        if config.resolution > 0:

            measured_value = (
                round(
                    measured_value
                    / config.resolution
                )
                * config.resolution
            )

        return measured_value


    # ========================================================
    # APPLY SENSOR FAULT
    # ========================================================

    @staticmethod
    def get_sensor_drift(
        sensor_fault: dict | None,
        sensor_name: str,
    ) -> float:
        """
        Extract drift value for a particular sensor.

        Compatible with faults/sensor_faults.py.
        """

        if sensor_fault is None:

            return 0.0

        fault_type = (
            sensor_fault.get(
                "type",
                "NONE"
            )
        )

        if fault_type != "SENSOR_DRIFT":

            return 0.0

        target_sensor = (
            sensor_fault.get(
                "target_sensor"
            )
        )

        if (
            target_sensor is None
            or target_sensor != sensor_name
        ):

            return 0.0

        severity = max(
            0.0,
            min(
                1.0,
                float(
                    sensor_fault.get(
                        "severity",
                        0.0
                    )
                )
            )
        )

        base_drift = float(
            sensor_fault.get(
                "drift_value",
                0.0
            )
        )

        return (
            base_drift
            * severity
        )


    # ========================================================
    # ARRAY MEASUREMENT
    # ========================================================

    def _measure_cylinder_array(
        self,
        sensor_type: str,
        values: list,
        sensor_fault: dict | None,
    ) -> list:
        """
        Measure a per-cylinder sensor array.
        """

        measured = []

        for index, value in enumerate(
            values,
            start=1
        ):

            sensor_name = (
                f"{sensor_type}_CYLINDER_{index}"
            )

            # Use the generic CHT/EGT sensor specification.
            specification_name = (
                sensor_type
            )

            drift = (
                self.get_sensor_drift(
                    sensor_fault,
                    sensor_name,
                )
            )

            # If a cylinder-specific sensor is not explicitly
            # configured, use the common sensor characteristics.

            config_name = (
                specification_name
            )

            config = (
                self.sensors[
                    config_name
                ]
            )

            noise = random.gauss(
                0.0,
                config.noise_std
            )

            observed = (
                float(value)
                + config.bias
                + drift
                + noise
            )

            observed = max(
                config.minimum,
                min(
                    config.maximum,
                    observed
                )
            )

            if config.resolution > 0:

                observed = (
                    round(
                        observed
                        / config.resolution
                    )
                    * config.resolution
                )

            measured.append(
                observed
            )

        return measured


    # ========================================================
    # MAIN SENSOR OBSERVATION
    # ========================================================

    def measure_engine(
        self,
        true_state: dict,
        sensor_fault: dict | None = None,
    ) -> SensorState:
        """
        Convert a true engine-state dictionary into a complete
        sensor observation.

        Expected true_state keys:

            rpm
            manifold_pressure_kpa
            intake_temperature_c
            fuel_flow_kg_s
            torque_nm
            power_kw

            cht_c
            egt_c

            oil_temperature_c
            oil_pressure_psi
            oil_flow_l_min

            battery_voltage_v
            battery_current_a
            battery_soc

            vibration_rms
            vibration_peak
            vibration_0_5x
            vibration_1x
            vibration_2x

        CHT and EGT are expected as four-element lists.
        """

        # ----------------------------------------------------
        # Helper
        # ----------------------------------------------------

        def read(
            sensor_name: str,
            key: str,
        ):

            true_value = float(
                true_state.get(
                    key,
                    0.0
                )
            )

            drift = (
                self.get_sensor_drift(
                    sensor_fault,
                    sensor_name,
                )
            )

            return self.measure(
                sensor_name,
                true_value,
                drift,
            )


        # ----------------------------------------------------
        # CHT
        # ----------------------------------------------------

        cht_values = true_state.get(
            "cht_c",
            [0.0, 0.0, 0.0, 0.0]
        )

        if len(cht_values) != 4:

            raise ValueError(
                "cht_c must contain "
                "exactly four cylinder values."
            )

        measured_cht = (
            self._measure_cylinder_array(
                "CHT",
                cht_values,
                sensor_fault,
            )
        )

        # ----------------------------------------------------
        # EGT
        # ----------------------------------------------------

        egt_values = true_state.get(
            "egt_c",
            [0.0, 0.0, 0.0, 0.0]
        )

        if len(egt_values) != 4:

            raise ValueError(
                "egt_c must contain "
                "exactly four cylinder values."
            )

        measured_egt = (
            self._measure_cylinder_array(
                "EGT",
                egt_values,
                sensor_fault,
            )
        )

        # ----------------------------------------------------
        # Scalar sensors
        # ----------------------------------------------------

        return SensorState(

            rpm=read(
                "RPM",
                "rpm",
            ),

            manifold_pressure_kpa=read(
                "MANIFOLD_PRESSURE",
                "manifold_pressure_kpa",
            ),

            intake_temperature_c=read(
                "INTAKE_TEMPERATURE",
                "intake_temperature_c",
            ),

            fuel_flow_kg_s=read(
                "FUEL_FLOW",
                "fuel_flow_kg_s",
            ),

            torque_nm=read(
                "TORQUE",
                "torque_nm",
            ),

            power_kw=read(
                "POWER",
                "power_kw",
            ),

            cht_cylinder_1_c=(
                measured_cht[0]
            ),

            cht_cylinder_2_c=(
                measured_cht[1]
            ),

            cht_cylinder_3_c=(
                measured_cht[2]
            ),

            cht_cylinder_4_c=(
                measured_cht[3]
            ),

            egt_cylinder_1_c=(
                measured_egt[0]
            ),

            egt_cylinder_2_c=(
                measured_egt[1]
            ),

            egt_cylinder_3_c=(
                measured_egt[2]
            ),

            egt_cylinder_4_c=(
                measured_egt[3]
            ),

            oil_temperature_c=read(
                "OIL_TEMPERATURE",
                "oil_temperature_c",
            ),

            oil_pressure_psi=read(
                "OIL_PRESSURE",
                "oil_pressure_psi",
            ),

            oil_flow_l_min=read(
                "OIL_FLOW",
                "oil_flow_l_min",
            ),

            battery_voltage_v=read(
                "BATTERY_VOLTAGE",
                "battery_voltage_v",
            ),

            battery_current_a=read(
                "BATTERY_CURRENT",
                "battery_current_a",
            ),

            battery_soc=read(
                "BATTERY_SOC",
                "battery_soc",
            ),

            vibration_rms=read(
                "VIBRATION_RMS",
                "vibration_rms",
            ),

            vibration_peak=read(
                "VIBRATION_PEAK",
                "vibration_peak",
            ),

            vibration_0_5x=read(
                "VIBRATION_0_5X",
                "vibration_0_5x",
            ),

            vibration_1x=read(
                "VIBRATION_1X",
                "vibration_1x",
            ),

            vibration_2x=read(
                "VIBRATION_2X",
                "vibration_2x",
            ),

            alternator_power_w=read(
                "ALTERNATOR_POWER",
                "alternator_power_w",
            ),

            injection_timing_nominal_deg=read(
                "INJECTION_TIMING",
                "injection_timing_nominal_deg",
            ),

            injection_timing_actual_deg=read(
                "INJECTION_TIMING",
                "injection_timing_actual_deg",
            ),

            injection_timing_deviation_deg=read(
                "INJECTION_TIMING",
                "injection_timing_deviation_deg",
            ),
        )


# ============================================================
# CONVERSION TO DICTIONARY
# ============================================================

def sensor_state_to_dict(
    state: SensorState,
) -> dict:
    """
    Convert SensorState to a flat dictionary.

    This format is convenient for:

        - CSV logging
        - pandas
        - ML preprocessing
        - MQTT
        - CAN gateway
    """

    return {

        "rpm":
            state.rpm,

        "manifold_pressure_kpa":
            state.manifold_pressure_kpa,

        "intake_temperature_c":
            state.intake_temperature_c,

        "fuel_flow_kg_s":
            state.fuel_flow_kg_s,

        "torque_nm":
            state.torque_nm,

        "power_kw":
            state.power_kw,

        "cht_cylinder_1_c":
            state.cht_cylinder_1_c,

        "cht_cylinder_2_c":
            state.cht_cylinder_2_c,

        "cht_cylinder_3_c":
            state.cht_cylinder_3_c,

        "cht_cylinder_4_c":
            state.cht_cylinder_4_c,

        "egt_cylinder_1_c":
            state.egt_cylinder_1_c,

        "egt_cylinder_2_c":
            state.egt_cylinder_2_c,

        "egt_cylinder_3_c":
            state.egt_cylinder_3_c,

        "egt_cylinder_4_c":
            state.egt_cylinder_4_c,

        "oil_temperature_c":
            state.oil_temperature_c,

        "oil_pressure_psi":
            state.oil_pressure_psi,

        "oil_flow_l_min":
            state.oil_flow_l_min,

        "battery_voltage_v":
            state.battery_voltage_v,

        "battery_current_a":
            state.battery_current_a,

        "battery_soc":
            state.battery_soc,

        "vibration_rms":
            state.vibration_rms,

        "vibration_peak":
            state.vibration_peak,

        "vibration_0_5x":
            state.vibration_0_5x,

        "vibration_1x":
            state.vibration_1x,

        "vibration_2x":
            state.vibration_2x,
            
        "alternator_power_w":
            state.alternator_power_w,
            
        "injection_timing_nominal_deg":
            state.injection_timing_nominal_deg,
            
        "injection_timing_actual_deg":
            state.injection_timing_actual_deg,
            
        "injection_timing_deviation_deg":
            state.injection_timing_deviation_deg,
    }


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    sensor_model = SensorModel(
        random_seed=42
    )

    # --------------------------------------------------------
    # Synthetic true engine state
    # --------------------------------------------------------

    true_engine = {

        "rpm":
            4000.0,

        "manifold_pressure_kpa":
            92.0,

        "intake_temperature_c":
            35.0,

        "fuel_flow_kg_s":
            0.0025,

        "torque_nm":
            120.0,

        "power_kw":
            50.3,

        "cht_c":
            [
                165.0,
                168.0,
                164.0,
                167.0,
            ],

        "egt_c":
            [
                690.0,
                700.0,
                685.0,
                695.0,
            ],

        "oil_temperature_c":
            95.0,

        "oil_pressure_psi":
            58.0,

        "oil_flow_l_min":
            5.5,

        "battery_voltage_v":
            24.2,

        "battery_current_a":
            2.5,

        "battery_soc":
            0.92,

        "vibration_rms":
            0.31,

        "vibration_peak":
            0.88,

        "vibration_0_5x":
            0.06,

        "vibration_1x":
            0.24,

        "vibration_2x":
            0.08,
    }

    # ========================================================
    # NORMAL SENSOR
    # ========================================================

    normal = (
        sensor_model.measure_engine(
            true_state=true_engine
        )
    )

    print(
        "\nAERIS-TWIN SENSOR MODEL"
    )

    print(
        "=" * 90
    )

    print(
        "\nTRUE vs MEASURED"
    )

    print(
        f"RPM: "
        f"{true_engine['rpm']:.2f}"
        f" -> "
        f"{normal.rpm:.2f}"
    )

    print(
        f"Oil pressure: "
        f"{true_engine['oil_pressure_psi']:.2f}"
        f" -> "
        f"{normal.oil_pressure_psi:.2f}"
    )

    print(
        f"Oil temperature: "
        f"{true_engine['oil_temperature_c']:.2f}"
        f" -> "
        f"{normal.oil_temperature_c:.2f}"
    )

    print(
        f"CHT Cylinder 3: "
        f"{true_engine['cht_c'][2]:.2f}"
        f" -> "
        f"{normal.cht_cylinder_3_c:.2f}"
    )

    # ========================================================
    # SENSOR DRIFT
    # ========================================================

    sensor_fault = {

        "type":
            "SENSOR_DRIFT",

        "target_sensor":
            "CHT_CYLINDER_3",

        "severity":
            0.80,

        "drift_value":
            15.0,
    }

    drifted = (
        sensor_model.measure_engine(

            true_state=true_engine,

            sensor_fault=sensor_fault,
        )
    )

    print(
        "\nSENSOR DRIFT TEST"
    )

    print(
        "=" * 90
    )

    print(
        f"True CHT Cylinder 3: "
        f"{true_engine['cht_c'][2]:.2f} °C"
    )

    print(
        f"Measured CHT Cylinder 3: "
        f"{drifted.cht_cylinder_3_c:.2f} °C"
    )

    print(
        "\nIMPORTANT:"
    )

    print(
        "The true engine temperature was NOT changed."
    )