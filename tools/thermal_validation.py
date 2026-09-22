import csv
from dataclasses import asdict

from simulation.engine_simulator import EngineSimulator
from intelligence.thermal_diagnostics import ThermalDiagnostics
from simulation.mission import MissionProfile


RESULT_FILE = "tools/thermal_physics_results.csv"

DT = 0.1
SIMULATION_SECONDS = 120.0
FAULT_START_S = 10.0
FAULT_SEVERITY = 0.85


def run_test(name, cooling_fault=False, high_altitude=False):
    simulator = EngineSimulator(
        timestep_s=DT,
        random_seed=42,
    )

    mission = MissionProfile()
    thermal_diagnostics = ThermalDiagnostics()

    rows = []
    history = []
    fault_activated = False

    steps = int(SIMULATION_SECONDS / DT)

    for step in range(steps):
        t = simulator.time_s

        # Get mission operating condition.
        inputs = mission.engine_inputs_at(t)

        # Independent high-altitude stress scenario.
        if high_altitude:
            inputs.altitude_m = max(
                inputs.altitude_m,
                8000.0,
            )

        # Inject cooling degradation directly into
        # the simulator's supported fault interface.
        if cooling_fault and not fault_activated and t >= FAULT_START_S:
            simulator.activate_cooling_fault(severity=FAULT_SEVERITY)
            fault_activated = True

        true_state, sensor_state = simulator.step(inputs)

        measured = asdict(sensor_state)

        cht = max(
            measured.get(
                "cht_cylinder_1_c",
                0.0,
            ),
            measured.get(
                "cht_cylinder_2_c",
                0.0,
            ),
            measured.get(
                "cht_cylinder_3_c",
                0.0,
            ),
            measured.get(
                "cht_cylinder_4_c",
                0.0,
            ),
        )

        egt = max(
            measured.get(
                "egt_cylinder_1_c",
                0.0,
            ),
            measured.get(
                "egt_cylinder_2_c",
                0.0,
            ),
            measured.get(
                "egt_cylinder_3_c",
                0.0,
            ),
            measured.get(
                "egt_cylinder_4_c",
                0.0,
            ),
        )

        sample = {
            "test": name,
            "time_s": true_state.time_s,
            "phase": mission.state_at(
                true_state.time_s
            ).phase.value,
            "rpm": measured.get(
                "rpm",
                0.0,
            ),
            "throttle_pct": true_state.throttle_pct,
            "altitude_m": true_state.altitude_m,
            "cht_c": cht,
            "egt_c": egt,
            "oil_temperature_c": measured.get(
                "oil_temperature_c",
                0.0,
            ),
            "fault_type": true_state.fault_type,
        }

        history.append(sample)

        # ThermalDiagnostics expects the history
        # in the same format as pipeline thermal history.
        thermal_history = history[-100:]

        sample["thermal_condition"] = (
            thermal_diagnostics.process(
                thermal_history
            )
        )

        rows.append(sample)

    return rows


def summarize(name, rows):
    if not rows:
        return

    first = rows[0]
    last = rows[-1]

    max_cht = max(
        r["cht_c"] for r in rows
    )

    max_egt = max(
        r["egt_c"] for r in rows
    )

    max_oil = max(
        r["oil_temperature_c"]
        for r in rows
    )

    states = []

    for row in rows:
        state = row[
            "thermal_condition"
        ]

        if state not in states:
            states.append(state)

    # Compare temperature before and after
    # cooling fault activation.
    pre_fault = [
        r for r in rows
        if r["time_s"] < FAULT_START_S
    ]

    post_fault = [
        r for r in rows
        if r["time_s"] >= FAULT_START_S
    ]

    pre_cht = (
        pre_fault[-1]["cht_c"]
        if pre_fault
        else first["cht_c"]
    )

    post_cht = (
        post_fault[-1]["cht_c"]
        if post_fault
        else last["cht_c"]
    )

    print(f"\n{name}")
    print("-" * 70)
    print(
        f"Simulation time : "
        f"{last['time_s']:.1f} s"
    )
    print(
        f"Maximum CHT     : "
        f"{max_cht:.2f} C"
    )
    print(
        f"Maximum EGT     : "
        f"{max_egt:.2f} C"
    )
    print(
        f"Maximum Oil     : "
        f"{max_oil:.2f} C"
    )
    print(
        f"Initial CHT     : "
        f"{first['cht_c']:.2f} C"
    )
    print(
        f"Final CHT       : "
        f"{last['cht_c']:.2f} C"
    )
    print(
        f"Final CHT phase : "
        f"{last['phase']}"
    )
    print(
        f"Thermal states  : "
        f"{' -> '.join(states)}"
    )

    if "Cooling" in name:
        print(
            f"CHT before fault: "
            f"{pre_cht:.2f} C"
        )
        print(
            f"CHT after fault : "
            f"{post_cht:.2f} C"
        )
        print(
            f"Fault delta CHT : "
            f"{post_cht - pre_cht:+.2f} C"
        )


def main():
    print("=" * 80)
    print("AERIS-TWIN THERMAL PHYSICS VALIDATION")
    print("=" * 80)

    print(
        "\nRunning 120 seconds of simulation "
        "directly through EngineSimulator."
    )

    print(
        "No HTTP/server timing involved."
    )

    healthy = run_test(
        "Healthy",
        cooling_fault=False,
    )

    cooling = run_test(
        "Cooling Degradation",
        cooling_fault=True,
    )

    high_altitude = run_test(
        "High Altitude",
        high_altitude=True,
    )

    all_rows = (
        healthy
        + cooling
        + high_altitude
    )

    with open(
        RESULT_FILE,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=all_rows[0].keys(),
        )
        writer.writeheader()
        writer.writerows(all_rows)

    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)

    summarize(
        "HEALTHY BASELINE",
        healthy,
    )

    summarize(
        "COOLING DEGRADATION",
        cooling,
    )

    summarize(
        "HIGH ALTITUDE",
        high_altitude,
    )

    print("\n" + "=" * 80)
    print(
        f"CSV saved: {RESULT_FILE}"
    )
    print("=" * 80)


if __name__ == "__main__":
    main()
