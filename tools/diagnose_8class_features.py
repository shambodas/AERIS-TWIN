import sys
import csv
from pathlib import Path

# Add root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from simulation.engine_simulator import EngineSimulator, EngineInputs
from intelligence.pipeline import IntelligencePipeline

def main():
    sim = EngineSimulator()
    pipeline = IntelligencePipeline(root_dir=root_dir)

    classes_to_test = [
        "COOLING_DEGRADATION",
        "COMBUSTION_INSTABILITY",
        "INJECTOR_ABNORMALITY"
    ]
    
    features_list = [
        "rpm", "throttle_pct", "altitude_m", "fuel_flow_kg_s",
        "oil_temperature_c", "oil_pressure_psi", "vibration_rms",
        "cht_deviation", "egt_deviation", "oil_temperature_deviation",
        "oil_pressure_deviation", "fuel_flow_deviation", "vibration_deviation",
        "alternator_power_deviation", "injection_timing_deviation_deg"
    ]

    csv_rows = []

    print("=========================================")
    print("DIAGNOSE ML FEATURES: 3 FAILING CLASSES")
    print("=========================================\n")

    for cls in classes_to_test:
        sim.reset()
        sim.clear_faults()
        pipeline.reset_history()
        try:
            pipeline.reset_rul_state()
        except AttributeError:
            pass

        severity = 0.8
        if cls == "COOLING_DEGRADATION":
            sim.activate_cooling_fault(severity=severity)
        elif cls == "COMBUSTION_INSTABILITY":
            sim.activate_combustion_instability(severity=severity)
        elif cls == "INJECTOR_ABNORMALITY":
            sim.activate_injector_fault(severity=severity)

        inputs = EngineInputs(throttle_pct=80.0, altitude_m=0.0, airspeed_mps=0.0)

        for _ in range(50):
            true_state, sensor_state = sim.step(inputs)

        pred_dict = {}
        for _ in range(10):
            true_state, sensor_state = sim.step(inputs)
            pred_dict = pipeline.process(true_state, sensor_state)
            
        features = pred_dict.get("features", {})
        fault_classification = pred_dict.get("fault_classification", {})
        predicted_class = fault_classification.get("fault_type", "UNKNOWN")
        confidence = fault_classification.get("confidence", 0.0)
        anomaly = pred_dict.get("anomaly", {})
        anomaly_score = anomaly.get("score", 0.0)

        print(f"--- GROUND TRUTH: {cls} ---")
        print(f"Predicted Fault: {predicted_class}")
        print(f"Confidence:      {confidence:.3f}")
        print(f"Anomaly Score:   {anomaly_score:.3f}")
        print(f"Measured Inj Timing: {getattr(sensor_state, 'injection_timing_actual_deg', 0.0):.2f}")
        print(f"Measured Alt Power:  {getattr(sensor_state, 'alternator_power_w', 0.0):.2f}")
        print(f"Measured Oil Press:  {getattr(sensor_state, 'oil_pressure_psi', 0.0):.2f}")
        print(f"Measured Vib RMS:    {getattr(sensor_state, 'vibration_rms', 0.0):.3f}")
        print(f"Measured CHT Cyl 1:  {getattr(sensor_state, 'cht_cylinder_1_c', 0.0):.2f}")
        print(f"Measured EGT Cyl 1:  {getattr(sensor_state, 'egt_cylinder_1_c', 0.0):.2f}")
        print("ML Features:")
        for feat in features_list:
            print(f"  {feat}: {features.get(feat, 0.0)}")
        print("\n")

        row = {
            "true_class": cls,
            "predicted_class": predicted_class,
            "confidence": confidence,
            "anomaly_score": anomaly_score,
            "measured_injection_timing_deg": getattr(sensor_state, 'injection_timing_actual_deg', 0.0),
            "measured_alternator_power_w": getattr(sensor_state, 'alternator_power_w', 0.0),
            "measured_oil_pressure_psi": getattr(sensor_state, 'oil_pressure_psi', 0.0),
            "measured_vibration_rms": getattr(sensor_state, 'vibration_rms', 0.0),
            "measured_cht_cylinder_1_c": getattr(sensor_state, 'cht_cylinder_1_c', 0.0),
            "measured_egt_cylinder_1_c": getattr(sensor_state, 'egt_cylinder_1_c', 0.0),
        }
        for feat in features_list:
            row[feat] = features.get(feat, 0.0)
        
        csv_rows.append(row)

    out_csv = root_dir / "tools" / "diagnose_8class_features.csv"
    with open(out_csv, "w", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)

if __name__ == "__main__":
    main()
