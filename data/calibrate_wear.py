#!/usr/bin/env python3
"""
AERIS-TWIN Wear Equation Calibration

Used to determine an appropriate wear increment equation that provides meaningful
stage coverage and responds to operating conditions.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from simulation.engine_simulator import EngineSimulator, EngineInputs

def test_equation(name, calc_wear_fn, profiles):
    print(f"--- Testing Equation: {name} ---")
    
    for profile_name, inputs in profiles.items():
        sim = EngineSimulator(timestep_s=0.01, wear_rate_multiplier=0.0)
        
        # stabilize
        for _ in range(5000):
            true_state, sensor_state = sim.step(inputs)
            
        rpm = true_state.rpm
        cht = max(true_state.cht_c)
        
        wear_increment_per_tick = calc_wear_fn(rpm, cht, inputs.throttle_pct, sim.dt)
        
        if wear_increment_per_tick > 0:
            ticks_to_eol = 1.0 / wear_increment_per_tick
            seconds_to_eol = ticks_to_eol * sim.dt
        else:
            seconds_to_eol = float('inf')
            
        print(f"Profile: {profile_name:<10} | RPM: {rpm:<6.1f} | CHT: {cht:<5.1f} | Throttle: {inputs.throttle_pct:<4.1f}% | Est EOL (s): {seconds_to_eol:<7.1f}")
        
    print()

def main():
    profiles = {
        "GENTLE": EngineInputs(throttle_pct=55.0, altitude_m=5000.0),
        "NOMINAL": EngineInputs(throttle_pct=75.0, altitude_m=3000.0),
        "HARSH": EngineInputs(throttle_pct=95.0, altitude_m=1000.0, mission_phase="LOITER")
    }
    
    base_mult = 100.0
    
    def eq_linear(rpm, cht, throttle, dt):
        rf = max(0.0, rpm / 4000.0)
        tf = max(1.0, cht / 150.0)
        return 0.0001 * rf * tf * dt * base_mult * (throttle/75.0)
        
    def eq_quadratic(rpm, cht, throttle, dt):
        rf = max(0.0, rpm / 4000.0)
        tf = max(1.0, cht / 150.0)
        return 0.0001 * (rf**2) * (tf**2) * dt * base_mult * (throttle/75.0)

    def eq_cubic(rpm, cht, throttle, dt):
        rf = max(0.0, rpm / 4000.0)
        tf = max(1.0, cht / 150.0)
        return 0.0001 * (rf**3) * (tf**3) * dt * base_mult * (throttle/75.0)

    test_equation("Linear", eq_linear, profiles)
    test_equation("Quadratic", eq_quadratic, profiles)
    test_equation("Cubic", eq_cubic, profiles)

if __name__ == "__main__":
    main()
