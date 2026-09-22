import pytest
import os
import tempfile
import csv
from pathlib import Path
from simulation.engine_simulator import EngineSimulator, EngineInputs
from data.generate_rul_dataset import generate_trajectory

def test_wear_monotonicity():
    simulator = EngineSimulator(timestep_s=0.01, wear_rate_multiplier=100.0)
    inputs = EngineInputs(throttle_pct=80.0)
    
    wear_values = []
    for _ in range(100):
        simulator.step(inputs)
        wear_values.append(simulator.wear_index)
        
    for i in range(1, len(wear_values)):
        assert wear_values[i] >= wear_values[i-1], "Wear index must be monotonically non-decreasing"

def test_rul_and_eol_state():
    simulator = EngineSimulator(timestep_s=0.1, wear_rate_multiplier=500.0)
    inputs = EngineInputs(throttle_pct=90.0)
    
    # Run until failure
    max_steps = 10000
    for _ in range(max_steps):
        true_state, sensor_state = simulator.step(inputs)
        if simulator.failed:
            break
            
    assert simulator.failed, "Simulator should have reached FAILED state"
    assert simulator.wear_index >= 1.0, "Wear index should be >= 1.0 at EOL"
    assert simulator.eol_timestamp is not None
    assert true_state.fault_type == "ENGINE_FAILURE"
    assert true_state.rpm == 0.0

def test_normal_regression():
    # By default, wear_rate_multiplier is 0.0
    simulator = EngineSimulator(timestep_s=0.01)
    inputs = EngineInputs(throttle_pct=80.0)
    
    for _ in range(100):
        simulator.step(inputs)
        
    assert simulator.wear_index == 0.0, "Wear index should remain 0.0 during normal operation"
    assert not simulator.failed

def test_reproducibility():
    simulator1 = EngineSimulator(timestep_s=0.1, wear_rate_multiplier=500.0, random_seed=42)
    simulator2 = EngineSimulator(timestep_s=0.1, wear_rate_multiplier=500.0, random_seed=42)
    
    inputs = EngineInputs(throttle_pct=75.0)
    
    time_to_fail_1 = None
    time_to_fail_2 = None
    
    for _ in range(10000):
        simulator1.step(inputs)
        if simulator1.failed:
            time_to_fail_1 = simulator1.eol_timestamp
            break
            
    for _ in range(10000):
        simulator2.step(inputs)
        if simulator2.failed:
            time_to_fail_2 = simulator2.eol_timestamp
            break
            
    assert time_to_fail_1 is not None
    assert time_to_fail_1 == time_to_fail_2

def test_trajectory_diversity():
    sim_gentle = EngineSimulator(timestep_s=0.1, wear_rate_multiplier=500.0, random_seed=42)
    sim_harsh = EngineSimulator(timestep_s=0.1, wear_rate_multiplier=500.0, random_seed=42)
    
    inputs_gentle = EngineInputs(throttle_pct=50.0, altitude_m=5000.0)
    inputs_harsh = EngineInputs(throttle_pct=100.0, altitude_m=1000.0, mission_phase="LOITER")
    
    time_gentle = None
    time_harsh = None
    
    for _ in range(10000):
        if not sim_gentle.failed:
            sim_gentle.step(inputs_gentle)
            if sim_gentle.failed:
                time_gentle = sim_gentle.eol_timestamp
                
        if not sim_harsh.failed:
            sim_harsh.step(inputs_harsh)
            if sim_harsh.failed:
                time_harsh = sim_harsh.eol_timestamp
                
        if sim_gentle.failed and sim_harsh.failed:
            break
            
    assert time_harsh < time_gentle, "Harsh operating conditions should cause earlier EOL"

def test_dataset_generator_diversity_and_rul():
    with tempfile.TemporaryDirectory() as tmpdir:
        res1 = generate_trajectory("run_test1", 42, 100.0, "NOMINAL", tmpdir)
        res2 = generate_trajectory("run_test2", 43, 100.0, "NOMINAL", tmpdir)
        
        # Verify physical diversity across different seeds
        assert res1["duration_s"] != res2["duration_s"], "Different seeds should produce different EOL times due to latent parameters"
        
        # Verify stage coverage exists
        for stage in ["HEALTHY", "EARLY", "MODERATE", "ADVANCED", "CRITICAL"]:
            assert res1["stages"][stage] > 0, f"Trajectory missing {stage} stage"
            
        # Verify RUL constraints on output CSV
        csv_path = Path(res1["file"])
        rul_values = []
        wear_values = []
        
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rul_values.append(float(row["rul_seconds"]))
                wear_values.append(float(row["wear_index"]))
                
        # RUL >= 0
        assert min(rul_values) >= 0.0, "RUL cannot be negative"
        
        # RUL(EOL) == 0
        assert rul_values[-1] == 0.0, "Final RUL must be exactly 0.0"
        
        # RUL monotonic non-increasing
        for i in range(1, len(rul_values)):
            assert rul_values[i] <= rul_values[i-1], "RUL must be monotonically non-increasing"
            
        # Wear index hidden from output feature set?
        # Note: We output wear_index in the dataset for analysis right now, but the prompt
        # said "latent parameters... must not become observable runtime feature".
        # We did not include wear_rate_multiplier or initial_wear in the CSV.
        with open(csv_path, 'r') as f:
            header = f.readline()
            assert "wear_rate_multiplier" not in header
            assert "initial_wear" not in header

