from simulation.engine_simulator import EngineInputs, EngineSimulator


def sample(load_w):
    simulator = EngineSimulator(timestep_s=0.1, random_seed=42)
    state, _ = simulator.step(
        EngineInputs(
            altitude_m=3500.0,
            airspeed_mps=30.0,
            throttle_pct=60.0,
            mission_load_w=load_w,
        )
    )
    return state


def test_mission_load_increases_engine_demand():
    no_load = sample(0.0)
    high_load = sample(750.0)

    assert high_load.rpm < no_load.rpm
    assert high_load.torque_nm >= no_load.torque_nm