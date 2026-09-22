import json
from simulation.engine_simulator import EngineSimulator, EngineInputs
from intelligence.pipeline import IntelligencePipeline

def main():
    sim = EngineSimulator()
    inputs = EngineInputs(altitude_m=0.0, airspeed_mps=40.0, throttle_pct=75.0)
    
    intel = IntelligencePipeline()
    
    # Run steady state for a few steps
    for _ in range(10):
        true_state, sensor_state = sim.step(inputs)
    
    expected = intel.expectation_engine.calculate(operating_state={"rpm": true_state.rpm, "altitude_m": 0.0, "ambient_temperature_c": 15.0, "throttle_pct": 75.0, "load_pct": 75.0, "air_density_kg_m3": 1.225, "pressure_kpa": 101.0, "power_kw": true_state.power_kw, "torque_nm": true_state.torque_nm, "time_s": sim.time_s}, measured_state={})
    print("Normal expected oil pressure:", expected.get("expected_oil_pressure"))
    print("Normal actual oil pressure:", true_state.oil_pressure_psi)
    
    # Activate fault
    print("Activating low oil pressure fault...")
    sim.activate_lubrication_fault(severity=0.85)
    
    for i in range(10):
        true_state, sensor_state = sim.step(inputs)
        result = intel.process(true_state, sensor_state, timestamp=sim.time_s)
    
    print(f"\n--- Low Oil Pressure Test Results ---")
    print(f"1. True fault type: {true_state.fault_type}, severity: {true_state.fault_severity}")
    print(f"2. Actual oil pressure: {true_state.oil_pressure_psi:.2f} psi")
    
    expected_op = result.get("expected", {}).get("expected_oil_pressure", "N/A")
    if isinstance(expected_op, float):
        print(f"3. Expected oil pressure: {expected_op:.2f} psi")
    else:
        print(f"3. Expected oil pressure: {expected_op}")
        
    op_dev = result.get("deviations", {}).get("oil_pressure_deviation", {})
    abs_dev = op_dev.get("absolute", "N/A")
    norm_dev = op_dev.get("normalized", "N/A")
    if isinstance(abs_dev, float):
        print(f"4. Oil pressure absolute deviation: {abs_dev:.2f}")
    else:
        print(f"4. Oil pressure absolute deviation: {abs_dev}")
        
    if isinstance(norm_dev, float):
        print(f"5. Oil pressure normalized deviation: {norm_dev:.2f}")
    else:
        print(f"5. Oil pressure normalized deviation: {norm_dev}")
    
    fault_class = result.get("fault_classification", {})
    predicted_fault = fault_class.get("fault_type", "UNKNOWN")
    confidence = fault_class.get("confidence", 0.0)
    probabilities = fault_class.get("probabilities", {})
    
    print(f"6. Predicted fault type: {predicted_fault}")
    if isinstance(confidence, float):
        print(f"7. Confidence: {confidence:.4f}")
    else:
        print(f"7. Confidence: {confidence}")
        
    print(f"8. Full class probabilities:")
    for cls, prob in probabilities.items():
        if isinstance(prob, float):
            print(f"   - {cls}: {prob:.4f}")
        else:
            print(f"   - {cls}: {prob}")
            
    print("\n==================================================")
    if predicted_fault == "OIL_PRESSURE_DEGRADATION":
        print("PASS")
    else:
        print("FAIL")
    print("==================================================")
    
if __name__ == "__main__":
    main()
