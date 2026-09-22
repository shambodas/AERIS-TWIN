"""
AERIS-TWIN
Main Application

Purpose
-------
Single entry point for the complete AERIS-TWIN prototype.

Pipeline
--------

Mission Profile
       |
       v
Engine Simulator
       |
       +----> Fault Injection
       |
       v
True Engine State
       |
       v
Sensor Model
       |
       +----> Data Logger
       |
       +----> CAN Telemetry
       |
       +----> MQTT Telemetry
       |
       v
ML / Analytics Layer
       |
       v
Dashboard

Run
---

    python main.py

Optional fault modes
--------------------

    python main.py --fault normal
    python main.py --fault misfire
    python main.py --fault cooling
    python main.py --fault combustion_instability
    python main.py --fault sensor_drift

The default execution uses simulation mode and does not require
physical CAN hardware or an MQTT broker.
"""


from pathlib import Path
import argparse
import csv
import json
import time


# ============================================================
# PROJECT IMPORTS
# ============================================================

from simulation.engine_simulator import (
    EngineSimulator,
)

from simulation.mission import (
    MissionProfile,
    MissionRunner,
)

from data.logger import (
    EngineDataLogger,
)

from telemetry.can import (
    CANTelemetryEncoder,
    SimulatedCANBus,
)

from telemetry.mqtt import (
    MQTTConfig,
    MQTTPublisher,
)


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = (
    Path(__file__).resolve().parent
)

DATA_DIRECTORY = (
    PROJECT_ROOT / "data"
)

OUTPUT_DIRECTORY = (
    DATA_DIRECTORY / "generated"
)


# ============================================================
# ARGUMENT PARSER
# ============================================================

def parse_arguments():

    parser = argparse.ArgumentParser(

        description=(
            "AERIS-TWIN integrated "
            "Digital Twin simulation"
        )
    )

    parser.add_argument(

        "--fault",

        type=str,

        default="normal",

        choices=[
            "normal",
            "misfire",
            "cooling_degradation",
            "combustion_instability",
            "sensor_drift",
            "oil_pressure_degradation",
            "excessive_vibration",
            "injector_abnormality",
        ],

        help=(
            "Fault scenario to inject."
        ),
    )

    parser.add_argument(

        "--fault-severity",

        type=float,

        default=0.80,

        help=(
            "Fault severity from 0.0 to 1.0."
        ),
    )

    parser.add_argument(

        "--duration",

        type=float,

        default=1275.0,

        help=(
            "Simulation duration in seconds."
        ),
    )

    parser.add_argument(

        "--timestep",

        type=float,

        default=0.1,

        help=(
            "Engine simulation timestep."
        ),
    )

    parser.add_argument(

        "--mqtt",

        action="store_true",

        help=(
            "Enable real MQTT publishing."
        ),
    )

    parser.add_argument(

        "--broker",

        type=str,

        default="localhost",

        help=(
            "MQTT broker hostname."
        ),
    )

    parser.add_argument(

        "--broker-port",

        type=int,

        default=1883,

        help=(
            "MQTT broker port."
        ),
    )

    return parser.parse_args()


# ============================================================
# VALIDATE ARGUMENTS
# ============================================================

def validate_arguments(
    args,
):

    if not (
        0.0
        <= args.fault_severity
        <= 1.0
    ):

        raise ValueError(
            "Fault severity must be "
            "between 0.0 and 1.0."
        )

    if args.duration <= 0:

        raise ValueError(
            "Duration must be positive."
        )

    if args.timestep <= 0:

        raise ValueError(
            "Timestep must be positive."
        )


# ============================================================
# FAULT CONFIGURATION
# ============================================================

def configure_fault(
    simulator: EngineSimulator,
    fault: str,
    severity: float,
):
    """
    Activate the selected project fault.

    Fault mapping:

        normal
            0

        misfire
            1

        cooling
            2

        combustion_instability
            3

        sensor_drift
            4

        lubrication
            5

        excessive_vibration
            6
    """

    if fault == "normal":

        simulator.clear_faults()

        return

    if fault == "misfire":

        simulator.activate_misfire(

            severity=severity,

            cylinder=3,
        )

        return

    if fault == "cooling_degradation":

        simulator.activate_cooling_fault(

            severity=severity
        )

        return

    if fault == "combustion_instability":

        simulator.activate_combustion_instability(

            severity=severity
        )

        return

    if fault == "sensor_drift":

        simulator.activate_sensor_drift(

            sensor_name=(
                "CHT_CYLINDER_3"
            ),

            drift_value=15.0,

            severity=severity,
        )

        return

    if fault == "oil_pressure_degradation":

        simulator.activate_lubrication_fault(

            severity=severity
        )

        return

    if fault == "excessive_vibration":

        simulator.activate_vibration_fault(

            severity=severity
        )

        return

    if fault == "injector_abnormality":

        simulator.activate_injector_fault(

            severity=severity
        )

        return

    raise ValueError(
        f"Unsupported fault: {fault}"
    )


# ============================================================
# PRINT HEADER
# ============================================================

def print_header():

    print(
        "\n"
        + "=" * 90
    )

    print(
        "                 AERIS-TWIN"
    )

    print(
        " AI-Enabled Digital Twin for Aero Piston Engine Health"
    )

    print(
        "=" * 90
    )


# ============================================================
# PRINT CONFIGURATION
# ============================================================

def print_configuration(
    args,
    mission: MissionProfile,
):

    print(
        "\nSIMULATION CONFIGURATION"
    )

    print(
        "-" * 90
    )

    print(
        f"Fault:              "
        f"{args.fault.upper()}"
    )

    print(
        f"Fault severity:     "
        f"{args.fault_severity:.2f}"
    )

    print(
        f"Requested duration: "
        f"{args.duration:.1f} s"
    )

    print(
        f"Time step:           "
        f"{args.timestep:.3f} s"
    )

    print(
        f"Mission duration:    "
        f"{mission.total_duration_s:.1f} s"
    )

    print(
        f"MQTT mode:           "
        f"{'REAL' if args.mqtt else 'SIMULATION'}"
    )


# ============================================================
# CREATE COMPONENTS
# ============================================================

def create_system(
    args,
):
    """
    Initialize all AERIS-TWIN components.
    """

    simulator = EngineSimulator(

        num_cylinders=4,

        timestep_s=args.timestep,

        random_seed=42,
    )

    mission = MissionProfile()

    mission_runner = MissionRunner(

        simulator=simulator,

        mission=mission,
    )

    logger = EngineDataLogger(

        output_directory=OUTPUT_DIRECTORY,

        filename=(
            f"aeris_twin_"
            f"{args.fault}.csv"
        ),
    )

    can_bus = (
        SimulatedCANBus()
    )

    mqtt_config = MQTTConfig(

        broker_host=args.broker,

        broker_port=args.broker_port,

        client_id=(
            "aeris-twin-edge"
        ),

        topic_prefix=(
            "aeris-twin"
        ),

        qos=1,
    )

    mqtt_publisher = MQTTPublisher(

        config=mqtt_config,

        simulation_mode=(
            not args.mqtt
        ),
    )

    return (

        simulator,

        mission,

        mission_runner,

        logger,

        can_bus,

        mqtt_publisher,
    )


# ============================================================
# RUN SIMULATION
# ============================================================

def run_system(
    args,
    simulator,
    mission,
    mission_runner,
    logger,
    can_bus,
    mqtt_publisher,
):
    """
    Execute the integrated Digital Twin.
    """

    # --------------------------------------------------------
    # Reset dataset
    # --------------------------------------------------------

    logger.clear()

    # --------------------------------------------------------
    # Configure fault
    # --------------------------------------------------------

    configure_fault(

        simulator,

        args.fault,

        args.fault_severity,
    )

    # --------------------------------------------------------
    # MQTT connection
    # --------------------------------------------------------

    mqtt_connected = (
        mqtt_publisher.connect()
    )

    if not mqtt_connected:

        print(
            "\nWARNING:"
        )

        print(
            "MQTT connection unavailable."
        )

        print(
            "Simulation will continue without MQTT."
        )

    # --------------------------------------------------------
    # Simulation limits
    # --------------------------------------------------------

    duration = min(

        args.duration,

        mission.total_duration_s,
    )

    number_of_steps = int(

        duration
        / simulator.dt
    )

    print(
        "\nRUNNING DIGITAL TWIN"
    )

    print(
        "-" * 90
    )

    print(
        f"Steps: {number_of_steps}"
    )

    print(
        f"Duration: {duration:.2f} s"
    )

    print()

    # --------------------------------------------------------
    # Main loop
    # --------------------------------------------------------

    start_time = time.perf_counter()

    last_fault_type = None

    can_frame_count = 0

    mqtt_message_count = 0

    records_logged = 0

    for step_number in range(
        number_of_steps
    ):

        # ----------------------------------------------------
        # Mission state
        # ----------------------------------------------------

        mission_time = (
            simulator.time_s
        )

        mission_state = (
            mission.state_at(
                mission_time
            )
        )

        # ----------------------------------------------------
        # Convert mission to engine input
        # ----------------------------------------------------

        engine_inputs = (
            mission.engine_inputs_at(
                mission_time
            )
        )

        # ----------------------------------------------------
        # Digital Twin step
        # ----------------------------------------------------

        true_state, sensor_state = (
            simulator.step(
                engine_inputs
            )
        )

        # ----------------------------------------------------
        # Data logger
        # ----------------------------------------------------

        logger.log_engine_state(

            true_state=true_state,

            sensor_state=sensor_state,

            mission_phase=(
                mission_state
                .phase
                .value
            ),

            mission_progress=(
                mission_state
                .mission_progress
            ),
        )

        records_logged += 1

        # ----------------------------------------------------
        # CAN
        # ----------------------------------------------------

        frames = (
            CANTelemetryEncoder
            .encode_all(

                sensor_state=sensor_state,

                fault_type=(
                    true_state
                    .fault_type
                ),

                fault_severity=(
                    true_state
                    .fault_severity
                ),

                fault_label=(
                    true_state
                    .fault_label
                ),
            )
        )

        for frame in frames:

            can_bus.send(
                frame
            )

        can_frame_count += len(
            frames
        )

        # ----------------------------------------------------
        # MQTT telemetry
        # ----------------------------------------------------

        telemetry_ok = (
            mqtt_publisher
            .publish_engine_telemetry(

                sensor_state=sensor_state,

                mission_phase=(
                    mission_state
                    .phase
                    .value
                ),

                simulation_time_s=(
                    true_state.time_s
                ),
            )
        )

        if telemetry_ok:

            mqtt_message_count += 1

        # ----------------------------------------------------
        # Fault event
        # ----------------------------------------------------

        current_fault = (
            true_state.fault_type
        )

        if (
            current_fault
            != last_fault_type
        ):

            mqtt_publisher.publish_fault(

                fault_type=current_fault,

                severity=(
                    true_state
                    .fault_severity
                ),

                fault_label=(
                    true_state
                    .fault_label
                ),

                simulation_time_s=(
                    true_state.time_s
                ),

                mission_phase=(
                    mission_state
                    .phase
                    .value
                ),
            )

            last_fault_type = (
                current_fault
            )

        # ----------------------------------------------------
        # Progress output
        # ----------------------------------------------------

        if (
            step_number % max(
                1,
                number_of_steps // 10
            )
            == 0
        ):

            progress = (
                step_number
                / max(
                    1,
                    number_of_steps
                )
                * 100.0
            )

            print(

                f"[{progress:>5.1f}%] "

                f"t={true_state.time_s:>7.1f}s | "

                f"{mission_state.phase.value:<22} | "

                f"RPM="
                f"{true_state.rpm:>7.1f} | "

                f"CHT3="
                f"{true_state.cht_c[2]:>7.1f}°C | "

                f"Fault="
                f"{true_state.fault_type}"
            )

    # --------------------------------------------------------
    # Runtime
    # --------------------------------------------------------

    elapsed = (
        time.perf_counter()
        - start_time
    )

    # --------------------------------------------------------
    # Disconnect
    # --------------------------------------------------------

    mqtt_publisher.disconnect()

    return {

        "records_logged":
            records_logged,

        "can_frames":
            can_frame_count,

        "mqtt_messages":
            mqtt_message_count,

        "runtime_s":
            elapsed,

        "final_true_state":
            simulator.last_true_state,

        "final_sensor_state":
            simulator.last_sensor_state,
    }


# ============================================================
# SAVE RUN SUMMARY
# ============================================================

def save_run_summary(
    args,
    mission,
    result,
):
    """
    Save metadata describing the simulation run.

    This makes each generated dataset traceable to its
    simulation configuration.
    """

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True
    )

    summary_path = (
        OUTPUT_DIRECTORY
        / (
            f"run_summary_"
            f"{args.fault}.json"
        )
    )

    final_state = (
        result["final_true_state"]
    )

    summary = {

        "project":
            "AERIS-TWIN",

        "fault":
            args.fault,

        "fault_severity":
            args.fault_severity,

        "requested_duration_s":
            args.duration,

        "actual_duration_s":
            min(
                args.duration,
                mission.total_duration_s
            ),

        "timestep_s":
            args.timestep,

        "mission_duration_s":
            mission.total_duration_s,

        "records_logged":
            result["records_logged"],

        "can_frames":
            result["can_frames"],

        "mqtt_messages":
            result["mqtt_messages"],

        "execution_time_s":
            result["runtime_s"],

        "final_fault_type":
            (
                final_state.fault_type
                if final_state
                else None
            ),

        "final_fault_label":
            (
                final_state.fault_label
                if final_state
                else None
            ),
    }

    with summary_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            summary,
            file,
            indent=4,
        )

    return summary_path


# ============================================================
# PRINT FINAL RESULTS
# ============================================================

def print_final_results(
    result,
    logger,
    summary_path,
):

    final_state = (
        result["final_true_state"]
    )

    final_sensor = (
        result["final_sensor_state"]
    )

    print(
        "\n"
        + "=" * 90
    )

    print(
        "AERIS-TWIN RUN COMPLETE"
    )

    print(
        "=" * 90
    )

    print(
        "\nSIMULATION METRICS"
    )

    print(
        "-" * 90
    )

    print(
        f"Records logged:       "
        f"{result['records_logged']}"
    )

    print(
        f"CAN frames generated: "
        f"{result['can_frames']}"
    )

    print(
        f"MQTT messages:        "
        f"{result['mqtt_messages']}"
    )

    print(
        f"Execution time:       "
        f"{result['runtime_s']:.3f} s"
    )

    if final_state is not None:

        print(
            "\nFINAL ENGINE STATE"
        )

        print(
            "-" * 90
        )

        print(
            f"RPM:              "
            f"{final_state.rpm:.1f}"
        )

        print(
            f"Power:            "
            f"{final_state.power_kw:.2f} kW"
        )

        print(
            f"Thrust:           "
            f"{final_state.thrust_n:.2f} N"
        )

        print(
            f"CHT C1:           "
            f"{final_state.cht_c[0]:.1f} °C"
        )

        print(
            f"CHT C3:           "
            f"{final_state.cht_c[2]:.1f} °C"
        )

        print(
            f"Oil temperature:  "
            f"{final_state.oil_temperature_c:.1f} °C"
        )

        print(
            f"Oil pressure:     "
            f"{final_state.oil_pressure_psi:.1f} psi"
        )

        print(
            f"Vibration RMS:    "
            f"{final_state.vibration_rms:.4f}"
        )

        print(
            f"Fault:            "
            f"{final_state.fault_type}"
        )

        print(
            f"Fault severity:   "
            f"{final_state.fault_severity:.2f}"
        )

        print(
            f"Fault label:      "
            f"{final_state.fault_label}"
        )

    if (
        final_state is not None
        and final_sensor is not None
    ):

        print(
            "\nTRUE vs MEASURED"
        )

        print(
            "-" * 90
        )

        print(

            f"CHT C3 true:      "
            f"{final_state.cht_c[2]:.2f} °C"
        )

        print(

            f"CHT C3 measured:  "
            f"{final_sensor.cht_cylinder_3_c:.2f} °C"
        )

    print(
        "\nOUTPUT"
    )

    print(
        "-" * 90
    )

    print(
        f"Dataset:           "
        f"{logger.filepath}"
    )

    print(
        f"Run summary:       "
        f"{summary_path}"
    )

    print(
        "\n"
        + "=" * 90
    )


# ============================================================
# MAIN
# ============================================================

def main():

    args = parse_arguments()

    validate_arguments(
        args
    )

    print_header()

    # --------------------------------------------------------
    # Initialize
    # --------------------------------------------------------

    (
        simulator,
        mission,
        mission_runner,
        logger,
        can_bus,
        mqtt_publisher,
    ) = create_system(
        args
    )

    print_configuration(
        args,
        mission,
    )

    # --------------------------------------------------------
    # Run
    # --------------------------------------------------------

    result = run_system(

        args=args,

        simulator=simulator,

        mission=mission,

        mission_runner=mission_runner,

        logger=logger,

        can_bus=can_bus,

        mqtt_publisher=mqtt_publisher,
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary_path = (
        save_run_summary(

            args=args,

            mission=mission,

            result=result,
        )
    )

    # --------------------------------------------------------
    # Final output
    # --------------------------------------------------------

    print_final_results(

        result=result,

        logger=logger,

        summary_path=summary_path,
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()

