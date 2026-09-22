import glob
import pandas as pd
from pathlib import Path
import json

def validate_dataset():
    csv_files = glob.glob(str(Path(__file__).parent / "rul_trajectories" / "*.csv"))
    if not csv_files:
        print("No CSV files found.")
        return

    print(f"Validating {len(csv_files)} trajectories...")

    profiles = {"GENTLE": 0, "NOMINAL": 0, "HARSH": 0}
    total_samples = 0
    issues = []
    
    for f in csv_files:
        path = Path(f)
        profile = path.stem.split("_")[-1].upper()
        if profile in profiles:
            profiles[profile] += 1
            
        try:
            df = pd.read_csv(f)
        except Exception as e:
            issues.append(f"Failed to read {path.name}: {e}")
            continue

        if len(df) == 0:
            issues.append(f"Empty trajectory: {path.name}")
            continue
            
        total_samples += len(df)
        
        # Check for missing values
        missing = df.isnull().sum().sum()
        if missing > 0:
            issues.append(f"Missing values found in {path.name}: {missing}")
            
        # Check monotonicity of RUL
        rul = df["rul_seconds"].values
        is_monotonic = all(x >= y for x, y in zip(rul, rul[1:]))
        if not is_monotonic:
            issues.append(f"RUL is not monotonically decreasing in {path.name}")
            
        # Check EOL
        if df["rul_seconds"].iloc[-1] != 0:
            issues.append(f"RUL does not reach 0 at EOL in {path.name} (last value: {df['rul_seconds'].iloc[-1]})")

        # Check leakage variables
        leakage_cols = ["latent_wear_rate", "base_load"]
        for col in leakage_cols:
            if col in df.columns:
                issues.append(f"LEAKAGE: Latent parameter {col} found in {path.name}")
                
    # Prepare Report
    report = [
        "============================================================",
        "AERIS-TWIN — RUL DATASET GENERATION REPORT",
        "============================================================",
        f"Total Trajectories: {len(csv_files)}",
        f"Total Samples: {total_samples}",
        f"GENTLE Profile Count: {profiles['GENTLE']}",
        f"NOMINAL Profile Count: {profiles['NOMINAL']}",
        f"HARSH Profile Count: {profiles['HARSH']}",
        "",
        "ISSUES FOUND:"
    ]
    
    if issues:
        report.extend([f" - {iss}" for iss in issues])
    else:
        report.append(" None. Dataset is structurally valid, monotonic, and free of direct ground-truth leakage.")
        
    report_text = "\n".join(report)
    print(report_text)
    
    # Save report
    report_path = Path(__file__).parent.parent / "RUL_DATASET_GENERATION_REPORT.txt"
    with open(report_path, "w") as f:
        f.write(report_text)
        
    print(f"\nReport saved to {report_path}")
    
if __name__ == "__main__":
    validate_dataset()
