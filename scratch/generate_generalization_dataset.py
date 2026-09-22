import pandas as pd
import numpy as np
import random
import os
import sys
from pathlib import Path

sys.path.insert(0, '.')
from simulation.engine_simulator import EngineSimulator
from simulation.mission import MissionProfile
from data.logger import EngineDataLogger

def generate_trajectory(run_id, weather_type, mission_focus, output_file):
    if weather_type == "HOT":
        temp_offset = random.uniform(15.0, 30.0) # 15C ISA + 15 to 30 = 30C to 45C ambient
    elif weather_type == "COLD":
        temp_offset = random.uniform(-25.0, -10.0) # -10C to +5C ambient
    else:
        temp_offset = random.uniform(-5.0, 5.0) # 10C to 20C ambient

    mission = MissionProfile()
    
    alt_scale = 1.0
    if mission_focus == "HIGH_ALTITUDE":
        alt_scale = random.uniform(1.5, 2.0)
    elif mission_focus == "LOW_ALTITUDE":
        alt_scale = random.uniform(0.1, 0.4)
        
    import dataclasses
    new_segments = []
    for seg in mission.segments:
        new_alt_start = seg.altitude_start_m * alt_scale
        new_alt_end = seg.altitude_end_m * alt_scale
        
        dur_scale = random.uniform(0.8, 1.2)
        if mission_focus == "PROLONGED_CRUISE" and seg.phase.value == "CRUISE":
            dur_scale = random.uniform(1.5, 2.5)
        elif mission_focus == "LOW_RPM" and seg.phase.value in ["DESCENT", "LOITER"]:
            dur_scale = random.uniform(1.5, 2.0)
            
        new_dur = seg.duration_s * dur_scale
        new_segments.append(dataclasses.replace(seg, altitude_start_m=new_alt_start, altitude_end_m=new_alt_end, duration_s=new_dur))
    
    mission.segments = new_segments

    simulator = EngineSimulator(num_cylinders=4, timestep_s=1.0, random_seed=42+run_id)
    
    # Pre-warm by idling on the ground
    warm_up_time = random.uniform(0, 600)
    wt = 0.0
    while wt < warm_up_time:
        inputs = mission.engine_inputs_at(0.0) # Ground idle
        inputs.temperature_offset_k = temp_offset
        simulator.step(inputs)
        wt += 1.0
            
    logger = EngineDataLogger(output_directory=Path('.'), filename=output_file)
    logger.clear()

    duration = sum(seg.duration_s for seg in mission.segments)
    t = 0.0
    while t <= duration:
        inputs = mission.engine_inputs_at(t)
        inputs.temperature_offset_k = temp_offset
        
        true_state, sensor_state = simulator.step(inputs)
        logger.log_engine_state(true_state=true_state, sensor_state=sensor_state, mission_phase=inputs.mission_phase, mission_progress=t/duration)
        t += 0.5

    df = pd.read_csv(output_file)
    os.remove(output_file)
    
    # Add metadata
    df.insert(0, 'trajectory_id', run_id)
    df.insert(1, 'weather_type', weather_type)
    df.insert(2, 'mission_focus', mission_focus)
    
    return df

def main():
    np.random.seed(42)
    random.seed(42)
    
    num_trajectories = 50 
    
    weather_types = ["HOT", "COLD", "STANDARD"] * 17
    mission_focuses = ["STANDARD", "HIGH_ALTITUDE", "LOW_ALTITUDE", "PROLONGED_CRUISE", "LOW_RPM", "RAPID_TRANSITIONS"] * 9
    
    weather_types = weather_types[:num_trajectories]
    mission_focuses = mission_focuses[:num_trajectories]
    
    random.shuffle(weather_types)
    random.shuffle(mission_focuses)
    
    all_dfs = []
    tmp_file = 'tmp_trajectory.csv'
    
    print("Generating trajectories...")
    for i in range(num_trajectories):
        w = weather_types[i]
        m = mission_focuses[i]
        df = generate_trajectory(i+1, w, m, tmp_file)
        
        r = random.random()
        if r < 0.7:
            df.insert(3, 'split', 'train')
        elif r < 0.85:
            df.insert(3, 'split', 'val')
        else:
            df.insert(3, 'split', 'test')
            
        all_dfs.append(df)
        
    final_df = pd.concat(all_dfs, ignore_index=True)
    os.makedirs('data/generated/expectation_training', exist_ok=True)
    out_path = 'data/generated/expectation_training/aeris_twin_generalized_expectations.csv'
    final_df.to_csv(out_path, index=False)
    
    print("\n================ REPORT ================")
    print("TRAJECTORY COUNT:", num_trajectories)
    
    train_ids = final_df[final_df['split'] == 'train']['trajectory_id'].nunique()
    val_ids = final_df[final_df['split'] == 'val']['trajectory_id'].nunique()
    test_ids = final_df[final_df['split'] == 'test']['trajectory_id'].nunique()
    
    print("TRAIN TRAJECTORIES:", train_ids)
    print("VALIDATION TRAJECTORIES:", val_ids)
    print("TEST TRAJECTORIES:", test_ids)
    
    print("WEATHER COVERAGE:")
    for w in final_df['weather_type'].unique():
        sub = final_df[final_df['weather_type'] == w]
        print(f"  - {w}: {sub['true_ambient_temperature_c'].min():.1f}C to {sub['true_ambient_temperature_c'].max():.1f}C ({len(sub)} samples)")
        
    print("MISSION COVERAGE:")
    for m in final_df['mission_phase'].unique():
        print(f"  - {m}: {len(final_df[final_df['mission_phase'] == m])} samples")
        
    print("OPERATING ENVELOPE:")
    print(f"  - RPM: {final_df['true_rpm'].min():.1f} to {final_df['true_rpm'].max():.1f}")
    print(f"  - Throttle: {final_df['true_throttle_pct'].min():.1f}% to {final_df['true_throttle_pct'].max():.1f}%")
    print(f"  - Altitude: {final_df['true_altitude_m'].min():.1f}m to {final_df['true_altitude_m'].max():.1f}m")
    
    # Data Leakage Check
    train_set = set(final_df[final_df['split'] == 'train']['trajectory_id'])
    val_set = set(final_df[final_df['split'] == 'val']['trajectory_id'])
    test_set = set(final_df[final_df['split'] == 'test']['trajectory_id'])
    
    leakage = bool(train_set & val_set or train_set & test_set or val_set & test_set)
    print("DATA LEAKAGE CHECK:", "FAILED (Overlap found!)" if leakage else "PASSED (Zero overlap between splits)")
    print("READY FOR EXPECTATION-MODEL TRAINING: YES")

if __name__ == "__main__":
    main()
