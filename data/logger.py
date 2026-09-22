"""
AERIS-TWIN
Engine Telemetry and Dataset Logger

Purpose
-------
Store Digital Twin simulation output in a structured,
ML-ready format.

The logger preserves:

    1. Mission information
    2. True physical engine state
    3. Sensor-observed state
    4. Fault information

Design principle
----------------

TRUE STATE
    = Digital Twin ground truth

MEASURED STATE
    = What onboard sensors report

FAULT LABEL
    = Known injected condition used for supervised ML

Storage
-------

Primary:
    CSV

Optional future backend:
    InfluxDB

The logger itself does not perform ML inference.
"""


from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
import csv
import json


# ============================================================
# CONSTANTS
# ============================================================

DEFAULT_DATA_DIRECTORY = (
    Path(__file__).resolve().parent
)

DEFAULT_CSV_FILENAME = (
    "aeris_twin_dataset.csv"
)


# ============================================================
# LOGGER
# ============================================================

class EngineDataLogger:
    """
    Structured logger for AERIS-TWIN simulation data.

    Features:

        - automatic directory creation
        - CSV logging
        - JSON-compatible records
        - true/measured state separation
        - fault labels
        - mission metadata
        - append mode
    """

    def __init__(
        self,
        output_directory: str | Path | None = None,
        filename: str = DEFAULT_CSV_FILENAME,
    ):

        if output_directory is None:

            output_directory = (
                DEFAULT_DATA_DIRECTORY
            )

        self.output_directory = Path(
            output_directory
        )

        self.output_directory.mkdir(
            parents=True,
            exist_ok=True
        )

        self.filepath = (
            self.output_directory
            / filename
        )

        self.fieldnames = None


    # ========================================================
    # VALUE SERIALIZATION
    # ========================================================

    @staticmethod
    def _serialize_value(value):
        """
        Convert Python / NumPy-like values into CSV-safe values.
        """

        if is_dataclass(value):

            return asdict(value)

        # Lists and tuples are stored as JSON strings so that
        # cylinder-wise CHT/EGT values remain recoverable.

        if isinstance(
            value,
            (list, tuple)
        ):

            return json.dumps(
                value
            )

        # Dictionaries are also serialized as JSON.

        if isinstance(
            value,
            dict
        ):

            return json.dumps(
                value
            )

        # Enum-like objects.

        if hasattr(
            value,
            "value"
        ):

            return value.value

        return value


    # ========================================================
    # FLATTEN ENGINE STATE
    # ========================================================

    @staticmethod
    def _flatten_state(
        state,
        prefix: str,
    ) -> dict:
        """
        Flatten a dataclass/dictionary into one level.

        Example:

            true_state.rpm

        becomes:

            true_rpm
        """

        if state is None:

            return {}

        if is_dataclass(state):

            state = asdict(
                state
            )

        if not isinstance(
            state,
            dict
        ):

            raise TypeError(
                "State must be a dataclass "
                "or dictionary."
            )

        flattened = {}

        for key, value in state.items():

            # Do not duplicate fault metadata here because
            # it is logged explicitly at record level.

            if key in {
                "fault_type",
                "fault_severity",
                "fault_label",
                "time_s",
            }:

                continue

            # NumPy arrays / lists are kept as one field.

            flattened[
                f"{prefix}_{key}"
            ] = (
                EngineDataLogger
                ._serialize_value(value)
            )

        return flattened


    # ========================================================
    # BUILD RECORD
    # ========================================================

    def build_record(
        self,
        true_state,
        sensor_state,
        mission_phase: str | None = None,
        mission_progress: float | None = None,
    ) -> dict:
        """
        Build one flat ML/telemetry record.

        Required information:

            true_state
            sensor_state

        Optional:

            mission_phase
            mission_progress
        """

        if true_state is None:

            raise ValueError(
                "true_state cannot be None."
            )

        if sensor_state is None:

            raise ValueError(
                "sensor_state cannot be None."
            )

        # ----------------------------------------------------
        # Timestamp
        # ----------------------------------------------------

        timestamp = (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        )

        # ----------------------------------------------------
        # Extract true state
        # ----------------------------------------------------

        true_dict = (
            asdict(true_state)
            if is_dataclass(true_state)
            else dict(true_state)
        )

        # ----------------------------------------------------
        # Extract sensor state
        # ----------------------------------------------------

        sensor_dict = (
            asdict(sensor_state)
            if is_dataclass(sensor_state)
            else dict(sensor_state)
        )

        # ----------------------------------------------------
        # Base record
        # ----------------------------------------------------

        record = {

            "timestamp_utc":
                timestamp,

            "simulation_time_s":
                true_dict.get(
                    "time_s",
                    0.0
                ),

            "mission_phase":
                mission_phase
                if mission_phase is not None
                else "UNKNOWN",

            "mission_progress":
                (
                    mission_progress
                    if mission_progress is not None
                    else 0.0
                ),

            "fault_type":
                true_dict.get(
                    "fault_type",
                    "NORMAL"
                ),

            "fault_severity":
                true_dict.get(
                    "fault_severity",
                    0.0
                ),

            "fault_label":
                true_dict.get(
                    "fault_label",
                    0
                ),
        }

        # ----------------------------------------------------
        # True engine state
        # ----------------------------------------------------

        for key, value in (
            self._flatten_state(
                true_state,
                "true"
            ).items()
        ):

            record[key] = value

        # ----------------------------------------------------
        # Sensor state
        # ----------------------------------------------------

        for key, value in (
            self._flatten_state(
                sensor_state,
                "measured"
            ).items()
        ):

            record[key] = value

        return record


    # ========================================================
    # WRITE ONE RECORD
    # ========================================================

    def log_record(
        self,
        record: dict,
    ):
        """
        Append one record to CSV.

        The CSV header is automatically created on the first
        write.
        """

        if not record:

            raise ValueError(
                "Cannot log an empty record."
            )

        # ----------------------------------------------------
        # Initialize field order
        # ----------------------------------------------------

        if self.fieldnames is None:

            self.fieldnames = list(
                record.keys()
            )

        # ----------------------------------------------------
        # Handle new fields
        # ----------------------------------------------------

        new_fields = [
            key
            for key in record.keys()
            if key not in self.fieldnames
        ]

        if new_fields:

            self._rewrite_with_new_fields(
                new_fields
            )

        # ----------------------------------------------------
        # Append record
        # ----------------------------------------------------

        file_exists = (
            self.filepath.exists()
            and self.filepath.stat().st_size > 0
        )

        with self.filepath.open(
            mode="a",
            newline="",
            encoding="utf-8",
        ) as csv_file:

            writer = csv.DictWriter(

                csv_file,

                fieldnames=self.fieldnames,

                extrasaction="ignore",
            )

            if not file_exists:

                writer.writeheader()

            writer.writerow(
                record
            )


    # ========================================================
    # REWRITE CSV
    # ========================================================

    def _rewrite_with_new_fields(
        self,
        new_fields: list[str],
    ):
        """
        Expand the CSV schema if a later record introduces a
        new field.

        This is mainly useful during development.
        Production schemas should ideally be fixed.
        """

        if not self.filepath.exists():

            self.fieldnames.extend(
                new_fields
            )

            return

        with self.filepath.open(
            mode="r",
            newline="",
            encoding="utf-8",
        ) as csv_file:

            reader = csv.DictReader(
                csv_file
            )

            existing_rows = list(
                reader
            )

            existing_fields = (
                reader.fieldnames
                or []
            )

        self.fieldnames = (
            list(existing_fields)
            + [
                field
                for field in new_fields
                if field not in existing_fields
            ]
        )

        with self.filepath.open(
            mode="w",
            newline="",
            encoding="utf-8",
        ) as csv_file:

            writer = csv.DictWriter(

                csv_file,

                fieldnames=self.fieldnames,
            )

            writer.writeheader()

            for row in existing_rows:

                writer.writerow(
                    row
                )


    # ========================================================
    # LOG ENGINE STATE
    # ========================================================

    def log_engine_state(
        self,
        true_state,
        sensor_state,
        mission_phase: str | None = None,
        mission_progress: float | None = None,
    ):
        """
        Build and immediately log one engine observation.
        """

        record = (
            self.build_record(

                true_state=true_state,

                sensor_state=sensor_state,

                mission_phase=(
                    mission_phase
                ),

                mission_progress=(
                    mission_progress
                ),
            )
        )

        self.log_record(
            record
        )

        return record


    # ========================================================
    # LOG SIMULATION RESULTS
    # ========================================================

    def log_simulation_results(
        self,
        results: list[dict],
    ):
        """
        Log results produced by MissionRunner.

        Expected structure:

            {
                "mission_time_s": ...,
                "mission_phase": ...,
                "mission_progress": ...,
                "true_state": ...,
                "sensor_state": ...
            }
        """

        if not results:

            return 0

        count = 0

        for result in results:

            self.log_engine_state(

                true_state=(
                    result["true_state"]
                ),

                sensor_state=(
                    result["sensor_state"]
                ),

                mission_phase=(
                    result.get(
                        "mission_phase"
                    )
                ),

                mission_progress=(
                    result.get(
                        "mission_progress"
                    )
                ),
            )

            count += 1

        return count


    # ========================================================
    # LOAD DATA
    # ========================================================

    def load_records(self) -> list[dict]:
        """
        Load the generated CSV back into Python.

        Useful for validation and ML preprocessing.
        """

        if not self.filepath.exists():

            return []

        with self.filepath.open(
            mode="r",
            newline="",
            encoding="utf-8",
        ) as csv_file:

            reader = csv.DictReader(
                csv_file
            )

            return list(
                reader
            )


    # ========================================================
    # CLEAR DATASET
    # ========================================================

    def clear(self):
        """
        Delete the current dataset.

        Useful when regenerating synthetic training data.
        """

        if self.filepath.exists():

            self.filepath.unlink()

        self.fieldnames = None


    # ========================================================
    # DATASET INFORMATION
    # ========================================================

    def get_info(self) -> dict:
        """
        Return basic dataset information.
        """

        records = (
            self.load_records()
        )

        fault_distribution = {}

        for record in records:

            fault = record.get(
                "fault_type",
                "UNKNOWN"
            )

            fault_distribution[
                fault
            ] = (
                fault_distribution.get(
                    fault,
                    0
                )
                + 1
            )

        return {

            "filepath":
                str(self.filepath),

            "records":
                len(records),

            "columns":
                (
                    len(
                        self.fieldnames
                    )
                    if self.fieldnames
                    else 0
                ),

            "fault_distribution":
                fault_distribution,
        }


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print(
        "\n"
        + "=" * 90
    )

    print(
        "AERIS-TWIN DATA LOGGER TEST"
    )

    print(
        "=" * 90
    )

    # --------------------------------------------------------
    # Import simulator
    # --------------------------------------------------------

    from simulation.engine_simulator import (
        EngineSimulator,
        EngineInputs,
    )

    # --------------------------------------------------------
    # Create simulator
    # --------------------------------------------------------

    simulator = EngineSimulator(
        timestep_s=0.01,
        random_seed=42,
    )

    # --------------------------------------------------------
    # Create logger
    # --------------------------------------------------------

    logger = EngineDataLogger(
        output_directory=(
            Path(__file__).resolve().parent
        ),
        filename="test_dataset.csv",
    )

    # Start clean for this test.

    logger.clear()

    # --------------------------------------------------------
    # Operating condition
    # --------------------------------------------------------

    inputs = EngineInputs(

        altitude_m=3000.0,

        airspeed_mps=40.0,

        throttle_pct=70.0,

        mission_load_w=300.0,
    )

    # --------------------------------------------------------
    # Generate normal data
    # --------------------------------------------------------

    print(
        "\nGenerating NORMAL data..."
    )

    for _ in range(100):

        true_state, sensor_state = (
            simulator.step(
                inputs
            )
        )

        logger.log_engine_state(

            true_state=true_state,

            sensor_state=sensor_state,

            mission_phase="CRUISE",

            mission_progress=0.20,
        )

    # --------------------------------------------------------
    # Generate misfire data
    # --------------------------------------------------------

    simulator.reset()

    simulator.activate_misfire(

        severity=0.85,

        cylinder=3,
    )

    print(
        "Generating MISFIRE data..."
    )

    for _ in range(100):

        true_state, sensor_state = (
            simulator.step(
                inputs
            )
        )

        logger.log_engine_state(

            true_state=true_state,

            sensor_state=sensor_state,

            mission_phase="CRUISE",

            mission_progress=0.25,
        )

    # --------------------------------------------------------
    # Generate cooling fault data
    # --------------------------------------------------------

    simulator.reset()

    simulator.activate_cooling_fault(
        severity=0.80
    )

    print(
        "Generating COOLING data..."
    )

    for _ in range(100):

        true_state, sensor_state = (
            simulator.step(
                inputs
            )
        )

        logger.log_engine_state(

            true_state=true_state,

            sensor_state=sensor_state,

            mission_phase="CRUISE",

            mission_progress=0.30,
        )

    # --------------------------------------------------------
    # Dataset information
    # --------------------------------------------------------

    info = logger.get_info()

    print(
        "\nDATASET INFORMATION"
    )

    print(
        "-" * 90
    )

    print(
        f"File: "
        f"{info['filepath']}"
    )

    print(
        f"Records: "
        f"{info['records']}"
    )

    print(
        f"Columns: "
        f"{info['columns']}"
    )

    print(
        "Fault distribution:"
    )

    for fault, count in (
        info["fault_distribution"]
        .items()
    ):

        print(
            f"    {fault:<28} "
            f"{count}"
        )

    print(
        "\nLOGGER TEST COMPLETE"
    )