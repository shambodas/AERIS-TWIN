#!/usr/bin/env python3
"""
AERIS-TWIN Run-to-Failure Dataset Generator.

Generates progressive degradation datasets for RUL prediction.
"""

import argparse
import csv
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict

# Adjust import path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from simulation.engine_simulator import EngineSimulator, EngineInputs


def get_stage_name(wear_index):
    if wear_index < 0.2:
        return "HEALTHY"
    elif wear_index < 0.4:
        return "EARLY"
    elif wear_index < 0.6:
        return "MODERATE"
    elif wear_index < 0.8:
        return "ADVANCED"
    elif wear_index < 1.0:
        return "CRITICAL"
    else:
        return "EOL"

def generate_trajectory(run_id, seed, base_wear_rate, profile, output_dir):
    """
    Generate a single run-to-failure trajectory with latent physical diversity.
    """
    random.seed(seed)
    
    # Latent Physical Diversity (NOT output to ML model)
    # --------------------------------------------------
    # Vary the exact wear multiplier by +/- 15%
    latent_wear_rate = base_wear_rate * random.uniform(0.85, 1.15)
    
    # Initial wear index between 0.0 and 0.05
    initial_wear = random.uniform(0.0, 0.05)
    
    # Ambient temperature variation (-10C to +10C around ISA 15C)
    ambient_temp_offset = random.uniform(-10.0, 10.0)
    
    # Base load variation (0 to 200W)
    load_variation = random.uniform(0.0, 200.0)
    
    # Configure simulation inputs based on profile with slight physical perturbations
    inputs = EngineInputs()
    if profile == "GENTLE":
        inputs.throttle_pct = 55.0 + random.uniform(-2.0, 2.0)
        inputs.altitude_m = 5000.0 + random.uniform(-200, 200)
    elif profile == "NOMINAL":
        inputs.throttle_pct = 75.0 + random.uniform(-2.0, 2.0)
        inputs.altitude_m = 3000.0 + random.uniform(-200, 200)
    elif profile == "HARSH":
        inputs.throttle_pct = 95.0 + random.uniform(-2.0, 2.0)
        inputs.altitude_m = 1000.0 + random.uniform(-200, 200)
        
    inputs.mission_load_w += load_variation

    # Create simulator with latent configuration
    simulator = EngineSimulator(
        timestep_s=0.01, 
        random_seed=seed,
        wear_rate_multiplier=latent_wear_rate
    )
    simulator.wear_index = initial_wear
    
    # We don't have direct access to set ambient temp easily in this simulator version,
    # but the altitude and throttle perturbations combined with wear rate variation
    # provide significant physical trajectory diversity.
    
    trajectory_data = []
    
    # 1 Hz sampling
    ticks_per_second = int(1.0 / simulator.dt)
    
    max_sim_seconds = 1000000 # safety limit
    stage_counts = {"HEALTHY": 0, "EARLY": 0, "MODERATE": 0, "ADVANCED": 0, "CRITICAL": 0, "EOL": 0}
    
    for sim_sec in range(max_sim_seconds):
        
        # Advance 1 second of simulation time
        for _ in range(ticks_per_second):
            true_state, sensor_state = simulator.step(inputs)
            if simulator.failed:
                break
                
        # Determine current stage
        stage = get_stage_name(simulator.wear_index)
        stage_counts[stage] += 1
                
        # Record state (Observable + Basic Physical, No Latent Info)
        record = {
            "time_s": true_state.time_s,
            "wear_index": simulator.wear_index,
            "profile": profile,
            "run_id": run_id,
        }
        
        # Add observable sensors
        sensor_dict = asdict(sensor_state)
        for k, v in sensor_dict.items():
            record[f"measured_{k}"] = v
            
        trajectory_data.append(record)
        
        if simulator.failed:
            break

    if not simulator.failed:
        print(f"Warning: Run {run_id} did not fail within limits.")
        return None
        
    eol_time = simulator.eol_timestamp
    
    # Post-process to add RUL
    for row in trajectory_data:
        row["rul_seconds"] = max(0.0, eol_time - row["time_s"])
        
    # Write to CSV
    output_path = Path(output_dir) / f"trajectory_{run_id}_{profile}.csv"
    
    fieldnames = list(trajectory_data[0].keys())
    
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(trajectory_data)
        
    return {
        "run_id": run_id,
        "profile": profile,
        "seed": seed,
        "duration_s": eol_time,
        "rows": len(trajectory_data),
        "stages": stage_counts,
        "file": str(output_path)
    }

def main():
    parser = argparse.ArgumentParser(description="Generate RUL run-to-failure dataset.")
    parser.add_argument("--runs", type=int, default=10, help="Number of trajectories per profile.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility.")
    parser.add_argument("--wear-rate", type=float, default=100.0, help="Base wear rate multiplier.")
    parser.add_argument("--output-dir", type=str, default="data/rul_trajectories", help="Output directory.")
    
    args = parser.parse_args()
    
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    profiles = ["GENTLE", "NOMINAL", "HARSH"]
    
    results = []
    
    print(f"Generating RUL dataset in {out_dir} ...")
    
    total_runs = args.runs * len(profiles)
    current_run = 0
    
    for profile in profiles:
        for i in range(args.runs):
            current_run += 1
            run_seed = args.seed + current_run * 73
            run_id = f"run_{current_run:03d}"
            print(f"Generating {run_id} ({profile}) with seed {run_seed} ...")
            res = generate_trajectory(
                run_id=run_id,
                seed=run_seed,
                base_wear_rate=args.wear_rate,
                profile=profile,
                output_dir=out_dir
            )
            if res:
                results.append(res)
                
    print("\nGeneration Complete. Summary:")
    print("-" * 125)
    print(f"{'Run':<8} | {'Profile':<8} | {'Seed':<6} | {'EOL(s)':<8} | {'Rows':<5} | {'HEALTHY':<8} | {'EARLY':<8} | {'MOD':<8} | {'ADV':<8} | {'CRIT':<8}")
    print("-" * 125)
    
    profile_stats = {p: {"count": 0, "eol_sum": 0, "rows_sum": 0, "min_eol": float('inf'), "max_eol": 0} for p in profiles}
    
    for r in results:
        p = r['profile']
        profile_stats[p]["count"] += 1
        profile_stats[p]["eol_sum"] += r["duration_s"]
        profile_stats[p]["rows_sum"] += r["rows"]
        profile_stats[p]["min_eol"] = min(profile_stats[p]["min_eol"], r["duration_s"])
        profile_stats[p]["max_eol"] = max(profile_stats[p]["max_eol"], r["duration_s"])
        
        st = r["stages"]
        print(f"{r['run_id']:<8} | {r['profile']:<8} | {r['seed']:<6} | {r['duration_s']:<8.1f} | {r['rows']:<5} | {st['HEALTHY']:<8} | {st['EARLY']:<8} | {st['MODERATE']:<8} | {st['ADVANCED']:<8} | {st['CRITICAL']:<8}")
    
    print("-" * 125)
    print("\nProfile Statistics:")
    for p in profiles:
        stats = profile_stats[p]
        if stats["count"] > 0:
            avg_eol = stats["eol_sum"] / stats["count"]
            avg_rows = stats["rows_sum"] / stats["count"]
            print(f"  {p:<8}: Avg EOL = {avg_eol:.1f}s, Min = {stats['min_eol']:.1f}s, Max = {stats['max_eol']:.1f}s, Avg Rows = {avg_rows:.1f}")

if __name__ == "__main__":
    main()
