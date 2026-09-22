"""
AERIS-TWIN
UAV Mission Profile Generator

Purpose
-------
Generate mission-dependent engine operating conditions for the
AERIS-TWIN Digital Twin.

The mission layer does NOT calculate engine physics.

It provides external operating conditions to:

    simulation/engine_simulator.py

The engine simulator then calculates the corresponding:

    atmosphere
    intake
    combustion
    torque
    propeller load
    thermal behaviour
    lubrication
    electrical behaviour
    vibration
    sensor observations

Mission phases
--------------

    1. GROUND
    2. TAKEOFF
    3. CLIMB
    4. CRUISE
    5. LOITER
    6. DESCENT
    7. LANDING

Design principle
----------------

Mission profile
        ↓
Operating conditions
        ↓
Engine Digital Twin
        ↓
Telemetry
        ↓
Fault detection / ML
"""


from dataclasses import dataclass
from enum import Enum


# ============================================================
# MISSION PHASES
# ============================================================

class MissionPhase(str, Enum):
    """
    Standard UAV mission phases used by the prototype.
    """

    GROUND = "GROUND"

    TAKEOFF = "TAKEOFF"

    CLIMB = "CLIMB"

    CRUISE = "CRUISE"

    LOITER = "LOITER"

    DESCENT = "DESCENT"

    LANDING = "LANDING"


# ============================================================
# MISSION SEGMENT
# ============================================================

@dataclass(frozen=True)
class MissionSegment:
    """
    One mission segment.

    duration_s:
        Segment duration.

    altitude_start_m:
        Starting altitude.

    altitude_end_m:
        Ending altitude.

    airspeed_start_mps:
        Starting true/representative airspeed.

    airspeed_end_mps:
        Ending airspeed.

    throttle_start_pct:
        Initial throttle command.

    throttle_end_pct:
        Final throttle command.

    electrical_load_w:
        Additional electrical load represented at the engine
        electrical subsystem.

    ground_load_torque_nm:
        Static mechanical holding load applied during ground
        operation.
    """

    phase: MissionPhase

    duration_s: float

    altitude_start_m: float

    altitude_end_m: float

    airspeed_start_mps: float

    airspeed_end_mps: float

    throttle_start_pct: float

    throttle_end_pct: float

    electrical_load_w: float

    ground_load_torque_nm: float = 0.0


# ============================================================
# MISSION STATE
# ============================================================

@dataclass
class MissionState:
    """
    Current interpolated mission operating condition.
    """

    time_s: float

    phase: MissionPhase

    altitude_m: float

    airspeed_mps: float

    throttle_pct: float

    electrical_load_w: float

    ground_load_torque_nm: float

    segment_elapsed_s: float

    mission_progress: float


# ============================================================
# MISSION PROFILE
# ============================================================

class MissionProfile:
    """
    AERIS-TWIN UAV mission profile.

    The default profile represents a generic MALE-UAV-style
    mission envelope rather than a particular aircraft.

    It is intentionally parameterized so that it can later be
    replaced with measured or operator-defined mission data.
    """

    def __init__(
        self,
        segments: list[MissionSegment] | None = None,
    ):

        if segments is None:

            segments = (
                self.default_profile()
            )

        if not segments:

            raise ValueError(
                "Mission profile cannot be empty."
            )

        self.segments = list(
            segments
        )

        self._validate_segments()

        # ----------------------------------------------------
        # Cumulative timeline
        # ----------------------------------------------------

        self._cumulative_times = []

        cumulative = 0.0

        for segment in self.segments:

            cumulative += (
                segment.duration_s
            )

            self._cumulative_times.append(
                cumulative
            )

        self.total_duration_s = (
            cumulative
        )


    # ========================================================
    # DEFAULT PROFILE
    # ========================================================

    @staticmethod
    def default_profile():
        """
        Return the default representative mission.

        Values are prototype operating conditions and should
        be calibrated against the target engine/UAV when real
        aircraft data becomes available.
        """

        return [

            # ------------------------------------------------
            # GROUND
            # ------------------------------------------------

            MissionSegment(

                phase=MissionPhase.GROUND,

                duration_s=30.0,

                altitude_start_m=0.0,

                altitude_end_m=0.0,

                airspeed_start_mps=0.0,

                airspeed_end_mps=0.0,

                throttle_start_pct=0.0,

                throttle_end_pct=0.0,

                electrical_load_w=250.0,

                ground_load_torque_nm=20.0,
            ),

            # ------------------------------------------------
            # TAKEOFF
            # ------------------------------------------------

            MissionSegment(

                phase=MissionPhase.TAKEOFF,

                duration_s=45.0,

                altitude_start_m=0.0,

                altitude_end_m=500.0,

                airspeed_start_mps=0.0,

                airspeed_end_mps=35.0,

                throttle_start_pct=85.0,

                throttle_end_pct=95.0,

                electrical_load_w=450.0,
            ),

            # ------------------------------------------------
            # CLIMB
            # ------------------------------------------------

            MissionSegment(

                phase=MissionPhase.CLIMB,

                duration_s=120.0,

                altitude_start_m=500.0,

                altitude_end_m=5000.0,

                airspeed_start_mps=35.0,

                airspeed_end_mps=42.0,

                throttle_start_pct=90.0,

                throttle_end_pct=82.0,

                electrical_load_w=400.0,
            ),

            # ------------------------------------------------
            # CRUISE
            # ------------------------------------------------

            MissionSegment(

                phase=MissionPhase.CRUISE,

                duration_s=300.0,

                altitude_start_m=5000.0,

                altitude_end_m=5000.0,

                airspeed_start_mps=42.0,

                airspeed_end_mps=45.0,

                throttle_start_pct=65.0,

                throttle_end_pct=68.0,

                electrical_load_w=350.0,
            ),

            # ------------------------------------------------
            # LOITER / ISR
            # ------------------------------------------------

            MissionSegment(

                phase=MissionPhase.LOITER,

                duration_s=600.0,

                altitude_start_m=5000.0,

                altitude_end_m=5000.0,

                airspeed_start_mps=45.0,

                airspeed_end_mps=43.0,

                throttle_start_pct=60.0,

                throttle_end_pct=62.0,

                electrical_load_w=500.0,
            ),

            # ------------------------------------------------
            # DESCENT
            # ------------------------------------------------

            MissionSegment(

                phase=MissionPhase.DESCENT,

                duration_s=120.0,

                altitude_start_m=5000.0,

                altitude_end_m=1000.0,

                airspeed_start_mps=43.0,

                airspeed_end_mps=38.0,

                throttle_start_pct=40.0,

                throttle_end_pct=10.0,

                electrical_load_w=300.0,
            ),

            # ------------------------------------------------
            # LANDING
            # ------------------------------------------------

            MissionSegment(

                phase=MissionPhase.LANDING,

                duration_s=60.0,

                altitude_start_m=1000.0,

                altitude_end_m=0.0,

                airspeed_start_mps=38.0,

                airspeed_end_mps=10.0,

                throttle_start_pct=10.0,

                throttle_end_pct=0.0,

                electrical_load_w=250.0,
            ),
        ]


    # ========================================================
    # VALIDATION
    # ========================================================

    def _validate_segments(self):
        """
        Validate mission definition.
        """

        for index, segment in enumerate(
            self.segments
        ):

            if segment.duration_s <= 0:

                raise ValueError(
                    f"Segment {index} duration "
                    "must be positive."
                )

            if segment.altitude_start_m < 0:

                raise ValueError(
                    f"Segment {index} has "
                    "negative starting altitude."
                )

            if segment.altitude_end_m < 0:

                raise ValueError(
                    f"Segment {index} has "
                    "negative ending altitude."
                )

            if not (
                0.0
                <= segment.throttle_start_pct
                <= 100.0
            ):

                raise ValueError(
                    f"Segment {index} starting "
                    "throttle must be 0-100%."
                )

            if not (
                0.0
                <= segment.throttle_end_pct
                <= 100.0
            ):

                raise ValueError(
                    f"Segment {index} ending "
                    "throttle must be 0-100%."
                )

            if segment.airspeed_start_mps < 0:

                raise ValueError(
                    f"Segment {index} has "
                    "negative starting airspeed."
                )

            if segment.airspeed_end_mps < 0:

                raise ValueError(
                    f"Segment {index} has "
                    "negative ending airspeed."
                )

            if segment.electrical_load_w < 0:

                raise ValueError(
                    f"Segment {index} has "
                    "negative electrical load."
                )

            if segment.ground_load_torque_nm < 0:

                raise ValueError(
                    f"Segment {index} has "
                    "negative ground load torque."
                )


    # ========================================================
    # GET SEGMENT
    # ========================================================

    def get_segment(
        self,
        time_s: float,
    ) -> MissionSegment:
        """
        Return the mission segment active at time_s.
        """

        if time_s < 0:

            raise ValueError(
                "time_s cannot be negative."
            )

        for index, end_time in enumerate(
            self._cumulative_times
        ):

            if time_s < end_time:

                return self.segments[
                    index
                ]

        # At the exact end of the mission,
        # return the final segment.
        return self.segments[-1]


    # ========================================================
    # SEGMENT START TIME
    # ========================================================

    def get_segment_start_time(
        self,
        segment_index: int,
    ) -> float:
        """
        Return absolute mission time at which a segment begins.
        """

        if not (
            0
            <= segment_index
            < len(self.segments)
        ):

            raise IndexError(
                "Invalid mission segment index."
            )

        if segment_index == 0:

            return 0.0

        return self._cumulative_times[
            segment_index - 1
        ]


    # ========================================================
    # INTERPOLATION
    # ========================================================

    @staticmethod
    def _interpolate(
        start: float,
        end: float,
        fraction: float,
    ) -> float:
        """
        Linear interpolation.
        """

        fraction = max(
            0.0,
            min(
                1.0,
                fraction
            )
        )

        return (
            start
            + (
                end - start
            )
            * fraction
        )


    # ========================================================
    # STATE AT TIME
    # ========================================================

    def state_at(
        self,
        time_s: float,
    ) -> MissionState:
        """
        Calculate mission operating conditions at a given time.
        """

        if time_s < 0:

            raise ValueError(
                "time_s cannot be negative."
            )

        # ----------------------------------------------------
        # Clamp to mission duration
        # ----------------------------------------------------

        effective_time = min(
            time_s,
            self.total_duration_s
        )

        cumulative_previous = 0.0

        selected_segment = (
            self.segments[-1]
        )

        segment_elapsed = (
            selected_segment.duration_s
        )

        for segment in self.segments:

            segment_end = (
                cumulative_previous
                + segment.duration_s
            )

            if (
                effective_time
                <= segment_end
            ):

                selected_segment = (
                    segment
                )

                segment_elapsed = max(
                    0.0,
                    effective_time
                    - cumulative_previous
                )

                break

            cumulative_previous = (
                segment_end
            )

        # ----------------------------------------------------
        # Interpolation fraction
        # ----------------------------------------------------

        if (
            selected_segment.duration_s
            > 0
        ):

            fraction = (
                segment_elapsed
                / selected_segment.duration_s
            )

        else:

            fraction = 0.0

        # ----------------------------------------------------
        # Operating conditions
        # ----------------------------------------------------

        altitude = self._interpolate(

            selected_segment
            .altitude_start_m,

            selected_segment
            .altitude_end_m,

            fraction,
        )

        airspeed = self._interpolate(

            selected_segment
            .airspeed_start_mps,

            selected_segment
            .airspeed_end_mps,

            fraction,
        )

        throttle = self._interpolate(

            selected_segment
            .throttle_start_pct,

            selected_segment
            .throttle_end_pct,

            fraction,
        )

        # ----------------------------------------------------
        # Mission progress
        # ----------------------------------------------------

        if self.total_duration_s > 0:

            progress = (
                effective_time
                / self.total_duration_s
            )

        else:

            progress = 1.0

        return MissionState(

            time_s=effective_time,

            phase=selected_segment.phase,

            altitude_m=altitude,

            airspeed_mps=airspeed,

            throttle_pct=throttle,

            electrical_load_w=(
                selected_segment
                .electrical_load_w
            ),

            ground_load_torque_nm=(
                selected_segment
                .ground_load_torque_nm
            ),

            segment_elapsed_s=(
                segment_elapsed
            ),

            mission_progress=(
                progress
            ),
        )


    # ========================================================
    # ENGINE INPUTS
    # ========================================================

    def engine_inputs_at(
        self,
        time_s: float,
    ):
        """
        Convert mission state into EngineInputs.

        Imported locally to avoid circular imports.
        """

        from simulation.engine_simulator import (
            EngineInputs
        )

        state = self.state_at(
            time_s
        )

        return EngineInputs(

            altitude_m=(
                state.altitude_m
            ),

            airspeed_mps=(
                state.airspeed_mps
            ),

            throttle_pct=(
                state.throttle_pct
            ),

            mission_load_w=(
                state.electrical_load_w
            ),

            ground_load_torque_nm=(
                state.ground_load_torque_nm
            ),

            mission_phase=(
                state.phase.value
            ),
        )


    # ========================================================
    # MISSION TIMES
    # ========================================================

    def sample_times(
        self,
        timestep_s: float = 1.0,
    ) -> list[float]:
        """
        Generate uniformly spaced mission timestamps.

        This is useful for:

            - simulation
            - dataset generation
            - plotting
            - telemetry playback
        """

        if timestep_s <= 0:

            raise ValueError(
                "timestep_s must be positive."
            )

        times = []

        current = 0.0

        while (
            current
            < self.total_duration_s
        ):

            times.append(
                current
            )

            current += timestep_s

        # Ensure final mission state exists.
        if (
            not times
            or times[-1]
            < self.total_duration_s
        ):

            times.append(
                self.total_duration_s
            )

        return times


    # ========================================================
    # SUMMARY
    # ========================================================

    def summary(self) -> list[dict]:
        """
        Return a compact mission summary.
        """

        result = []

        start_time = 0.0

        for segment in self.segments:

            end_time = (
                start_time
                + segment.duration_s
            )

            result.append({

                "phase":
                    segment.phase.value,

                "start_time_s":
                    start_time,

                "end_time_s":
                    end_time,

                "duration_s":
                    segment.duration_s,

                "altitude_start_m":
                    segment.altitude_start_m,

                "altitude_end_m":
                    segment.altitude_end_m,

                "airspeed_start_mps":
                    segment.airspeed_start_mps,

                "airspeed_end_mps":
                    segment.airspeed_end_mps,

                "throttle_start_pct":
                    segment.throttle_start_pct,

                "throttle_end_pct":
                    segment.throttle_end_pct,

                "electrical_load_w":
                    segment.electrical_load_w,
            })

            start_time = end_time

        return result


# ============================================================
# MISSION SIMULATION DRIVER
# ============================================================

class MissionRunner:
    """
    Connect MissionProfile with EngineSimulator.

    This class is deliberately thin.

    MissionProfile decides:

        where the UAV is
        how fast it is flying
        how much throttle is requested

    EngineSimulator decides:

        how the engine responds.
    """

    def __init__(
        self,
        simulator,
        mission: MissionProfile | None = None,
    ):

        self.simulator = simulator

        self.mission = (
            mission
            if mission is not None
            else MissionProfile()
        )


    # ========================================================
    # RUN
    # ========================================================

    def run(
        self,
        duration_s: float | None = None,
    ) -> list[dict]:
        """
        Run the Digital Twin across the mission.

        The simulator timestep controls the actual engine
        integration resolution.
        """

        if duration_s is None:

            duration_s = (
                self.mission.total_duration_s
            )

        if duration_s <= 0:

            raise ValueError(
                "duration_s must be positive."
            )

        duration_s = min(
            duration_s,
            self.mission.total_duration_s
        )

        results = []

        # ----------------------------------------------------
        # Number of simulation steps
        # ----------------------------------------------------

        number_of_steps = int(
            duration_s
            / self.simulator.dt
        )

        for _ in range(
            number_of_steps
        ):

            mission_time = (
                self.simulator.time_s
            )

            if (
                mission_time
                > duration_s
            ):

                break

            inputs = (
                self.mission
                .engine_inputs_at(
                    mission_time
                )
            )

            true_state, sensor_state = (
                self.simulator.step(
                    inputs
                )
            )

            results.append({

                "mission_time_s":
                    mission_time,

                "mission_phase":
                    self.mission
                    .state_at(
                        mission_time
                    )
                    .phase.value,

                "mission_progress":
                    self.mission
                    .state_at(
                        mission_time
                    )
                    .mission_progress,

                "true_state":
                    true_state,

                "sensor_state":
                    sensor_state,
            })

        return results


# ============================================================
# TEST / DEMONSTRATION
# ============================================================

if __name__ == "__main__":

    print(
        "\n"
        + "=" * 90
    )

    print(
        "AERIS-TWIN MISSION PROFILE"
    )

    print(
        "=" * 90
    )

    mission = (
        MissionProfile()
    )

    # --------------------------------------------------------
    # Mission summary
    # --------------------------------------------------------

    print(
        "\nMISSION SUMMARY"
    )

    print(
        "-" * 90
    )

    for segment in (
        mission.summary()
    ):

        print(

            f"{segment['phase']:<12} | "

            f"{segment['start_time_s']:>7.0f} - "
            f"{segment['end_time_s']:>7.0f} s | "

            f"ALT "
            f"{segment['altitude_start_m']:>5.0f}"
            f" → "
            f"{segment['altitude_end_m']:>5.0f} m | "

            f"THR "
            f"{segment['throttle_start_pct']:>5.1f}"
            f" → "
            f"{segment['throttle_end_pct']:>5.1f}%"
        )

    print(
        "-" * 90
    )

    print(
        f"Total mission duration: "
        f"{mission.total_duration_s:.1f} s"
    )

    # --------------------------------------------------------
    # Sample mission states
    # --------------------------------------------------------

    print(
        "\nSAMPLED MISSION STATES"
    )

    print(
        "-" * 90
    )

    sample_times = [

        0.0,

        30.0,

        75.0,

        150.0,

        400.0,

        800.0,

        1100.0,

        mission.total_duration_s,
    ]

    for time_s in sample_times:

        if (
            time_s
            > mission.total_duration_s
        ):

            continue

        state = (
            mission.state_at(
                time_s
            )
        )

        print(

            f"t={state.time_s:>7.1f}s | "

            f"{state.phase.value:<22} | "

            f"ALT={state.altitude_m:>7.1f}m | "

            f"V={state.airspeed_mps:>5.1f}m/s | "

            f"THR={state.throttle_pct:>5.1f}%"
        )

    # --------------------------------------------------------
    # Engine input test
    # --------------------------------------------------------

    print(
        "\nENGINE INPUT TEST"
    )

    print(
        "-" * 90
    )

    test_time = 450.0

    engine_inputs = (
        mission.engine_inputs_at(
            test_time
        )
    )

    print(
        f"Mission time: "
        f"{test_time:.1f} s"
    )

    print(
        f"Altitude: "
        f"{engine_inputs.altitude_m:.1f} m"
    )

    print(
        f"Airspeed: "
        f"{engine_inputs.airspeed_mps:.1f} m/s"
    )

    print(
        f"Throttle: "
        f"{engine_inputs.throttle_pct:.1f} %"
    )

    print(
        f"Electrical load: "
        f"{engine_inputs.mission_load_w:.1f} W"
    )

    print(
        "\nMISSION PROFILE TEST COMPLETE"
    )