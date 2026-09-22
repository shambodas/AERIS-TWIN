import pandas as pd
from typing import List, Tuple

def get_base_features() -> List[str]:
    return [
        "measured_rpm",
        "measured_manifold_pressure_kpa",
        "measured_intake_temperature_c",
        "measured_fuel_flow_kg_s",
        "measured_torque_nm",
        "measured_power_kw",
        "measured_cht_cylinder_1_c",
        "measured_cht_cylinder_2_c",
        "measured_cht_cylinder_3_c",
        "measured_cht_cylinder_4_c",
        "measured_egt_cylinder_1_c",
        "measured_egt_cylinder_2_c",
        "measured_egt_cylinder_3_c",
        "measured_egt_cylinder_4_c",
        "measured_oil_temperature_c",
        "measured_oil_pressure_psi",
        "measured_oil_flow_l_min",
        "measured_battery_voltage_v",
        "measured_battery_current_a",
        "measured_battery_soc",
        "measured_vibration_rms",
        "measured_vibration_peak",
        "measured_vibration_0_5x",
        "measured_vibration_1x",
        "measured_vibration_2x"
    ]

def get_ablation_features(model_type: str) -> List[str]:
    """
    Model A: Full feature model (all sensors + elapsed time)
    Model B: Operating-condition-only model (throttle, ambient, altitude, mach, etc. - no degradation sensors like vibration, temps)
    Model C: Elapsed-time-only model
    Model D: Physics residual + health + temporal degradation model WITHOUT elapsed simulation time
    """
    if model_type == "A":
        return get_base_features() + ["time_s"]
        
    elif model_type == "B":
        return [
            "measured_rpm",
            "measured_manifold_pressure_kpa",
            "measured_intake_temperature_c",
            "measured_fuel_flow_kg_s",
            "measured_torque_nm",
            "measured_power_kw"
        ]
        
    elif model_type == "C":
        return ["time_s"]
        
    elif model_type == "D":
        # All base features without 'time_s'
        return get_base_features()
        
    else:
        raise ValueError(f"Unknown model_type: {model_type}")

def compute_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute derived features for better RUL prediction.
    """
    df = df.copy()
    
    # We can add rolling features if desired, but for basic training, raw features are used.
    # Group by run_id to safely compute rolling means without leaking across trajectories
    # df['rolling_vibration_10s'] = df.groupby('run_id')['measured_vibration_mm_s'].transform(lambda x: x.rolling(10, min_periods=1).mean())
    
    return df
