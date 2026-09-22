import sys
from pathlib import Path
import csv

# Add root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from simulation.engine_simulator import EngineSimulator, EngineInputs
from intelligence.pipeline import IntelligencePipeline

def main():
    sim = EngineSimulator()
    pipeline = IntelligencePipeline()

    classes = [
        "normal",
        "misfire",
        "cooling_degradation",
        "combustion_instability",
        "sensor_drift",
        "oil_pressure_degradation",
        "excessive_vibration",
        "injector_abnormality"
    ]

    results = []
    passed = 0
    
    print("========================================")
    print("AERIS-TWIN CURRENT 8-CLASS ML REGRESSION")
    print("========================================")
    print("\nEXPECTED                  | PREDICTED                 | CONFIDENCE | PASS/FAIL")
    print("-" * 80)
    
    for cls in classes:
        # 1. Reset simulator & pipeline
        sim.reset()
        sim.clear_faults()
        pipeline.reset_history()
        try:
            pipeline.reset_rul_state()
        except AttributeError:
            pass # ignore if not implemented
        
        # 2. Activate fault
        severity = 0.8
        expected_class = cls.upper()
        if cls == "misfire":
            sim.activate_misfire(severity=severity)
        elif cls == "cooling_degradation":
            sim.activate_cooling_fault(severity=severity)
        elif cls == "combustion_instability":
            sim.activate_combustion_instability(severity=severity)
        elif cls == "sensor_drift":
            sim.activate_sensor_drift(severity=severity, sensor_name="CHT_CYLINDER_3", drift_value=15.0)
        elif cls == "oil_pressure_degradation":
            sim.activate_lubrication_fault(severity=severity)
        elif cls == "excessive_vibration":
            sim.activate_vibration_fault(severity=severity)
        elif cls == "injector_abnormality":
            sim.activate_injector_fault(severity=severity)
        
        inputs = EngineInputs(throttle_pct=80.0, altitude_m=0.0, airspeed_mps=0.0)
        
        # 3. Warm-up steps
        warmup_steps = 300 if cls == "cooling_degradation" else 50
        for _ in range(warmup_steps):
            true_state, sensor_state = sim.step(inputs)
            
        # 4. Inference loop (aggregate predictions or take the last one)
        pred_dict = {}
        for _ in range(10):
            true_state, sensor_state = sim.step(inputs)
            pred_dict = pipeline.process(true_state, sensor_state)
            
        fault_classification = pred_dict.get("fault_classification", {})
        predicted_class = fault_classification.get("fault_type", "UNKNOWN")
        confidence = fault_classification.get("confidence", 0.0)
        
        anomaly = pred_dict.get("anomaly", {})
        is_anomaly = anomaly.get("is_anomaly", False)
        anomaly_score = anomaly.get("score", 0.0)
        
        health_score = pred_dict.get("health", {}).get("score", 1.0)
        
        features = pred_dict.get("features", {})
        timing_dev = features.get("injection_timing_deviation_deg", 0.0)
        alt_power_dev = features.get("alternator_power_deviation", 0.0)
        
        # Check Pass/Fail
        is_pass = (predicted_class == expected_class)
        if is_pass:
            passed += 1
            
        print(f"{expected_class:25} | {predicted_class:25} | {confidence:.2f}       | {'PASS' if is_pass else 'FAIL'}")
        
        if not is_pass:
            print(f"  -> Diagnostics:")
            print(f"     Top Probabilities: {fault_classification.get('probabilities', {})}")
            print(f"     Anomaly Score: {anomaly_score:.3f}")
            print(f"     Injection Timing Dev: {timing_dev:.3f}")
            print(f"     Alternator Power Dev: {alt_power_dev:.3f}")
            
        results.append({
            "expected_class": expected_class,
            "predicted_class": predicted_class,
            "confidence": confidence,
            "anomaly_score": anomaly_score,
            "is_anomaly": is_anomaly,
            "health_score": health_score,
            "severity": severity if expected_class != "NORMAL" else 0.0,
            "injection_timing_deviation_deg": timing_dev,
            "alternator_power_deviation": alt_power_dev,
            "pass": is_pass
        })
        
    print(f"\nTotal: 8")
    print(f"Passed: {passed}")
    print(f"Failed: {8 - passed}")
    print(f"Accuracy: {passed}/8")
    
    # Save to CSV
    out_csv = root_dir / "tools" / "current_8class_ml_results.csv"
    with open(out_csv, "w", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        for r in results:
            writer.writerow(r)
            
if __name__ == "__main__":
    main()
