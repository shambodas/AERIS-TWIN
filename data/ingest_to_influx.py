import csv
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from database.influx_writer import InfluxWriter

def ingest_all():
    writer = InfluxWriter()
    csv_files = glob.glob(str(Path(__file__).parent / "rul_trajectories" / "*.csv"))
    
    if not csv_files:
        print("No CSV files found in data/rul_trajectories/")
        return

    print(f"Found {len(csv_files)} trajectory files. Ingesting into InfluxDB...")

    success_count = 0
    
    for file_path in csv_files:
        path = Path(file_path)
        # Format: profile_flightid.csv
        parts = path.stem.split("_")
        if len(parts) >= 2:
            profile = parts[0].upper()
            flight_id = "_".join(parts[1:])
        else:
            profile = "UNKNOWN"
            flight_id = path.stem
        
        telemetry_rows = []
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert string values to float where appropriate
                telemetry = {}
                for k, v in row.items():
                    # Exclude the metadata/target columns from raw telemetry
                    if k in ["time_s", "wear_index", "health_score", "rul_seconds", "flight_id", "profile"]:
                        continue
                    try:
                        telemetry[k] = float(v)
                    except ValueError:
                        pass # Ignore non-numeric strings
                
                # We do want timestamp if present, otherwise let InfluxWriter use current time.
                # Actually, the telemetry writer expects plain float values and will tag it with current time.
                telemetry_rows.append(telemetry)

        if not telemetry_rows:
            continue

        print(f"Ingesting {flight_id} ({profile}) - {len(telemetry_rows)} points")

        # Write telemetry points
        for point in telemetry_rows:
            writer.write_telemetry(point, flight_id=flight_id, mission_name=profile)
            
        # Write flight summary
        # Compute basic statistics
        max_altitude = max((r.get("altitude_m", 0.0) for r in telemetry_rows), default=0.0)
        max_rpm = max((r.get("rpm", 0.0) for r in telemetry_rows), default=0.0)
        max_cht = max(
            (max(r.get(f"cht_cylinder_{i}_c", 0.0) for i in range(1, 5)) for r in telemetry_rows), 
            default=0.0
        )
        max_egt = max(
            (max(r.get(f"egt_cylinder_{i}_c", 0.0) for i in range(1, 5)) for r in telemetry_rows), 
            default=0.0
        )
        max_vib = max((r.get("vibration_rms", 0.0) for r in telemetry_rows), default=0.0)
        
        stats = {
            "max_altitude_m": max_altitude,
            "max_rpm": max_rpm,
            "max_cht_c": max_cht,
            "max_egt_c": max_egt,
            "max_vibration_rms": max_vib,
            "minimum_health_score": 0.0, # EOL reached
            "final_health_score": 0.0,
            "fault_detected": True,
            "fault_type": "ENGINE_FAILURE",
            "fault_first_seen": datetime.now(timezone.utc).timestamp(),
            "fault_last_seen": datetime.now(timezone.utc).timestamp(),
            "fault_event_count": 1,
            "mission_progress": 100.0,
            "telemetry_points": len(telemetry_rows)
        }
        
        writer.write_flight_record(
            flight_id=flight_id,
            mission_name=profile,
            mission_key=profile.lower(),
            flight_status="FAILED",
            start_time=datetime.now(timezone.utc), # Using current time for ingestion
            end_time=datetime.now(timezone.utc),
            duration_seconds=len(telemetry_rows)*0.1,
            statistics=stats
        )
        
        success_count += 1
        
    print(f"Successfully ingested {success_count} trajectories.")

if __name__ == "__main__":
    ingest_all()
