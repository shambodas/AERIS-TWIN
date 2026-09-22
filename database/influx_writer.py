import os
import time
import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import ASYNCHRONOUS


class InfluxWriter:
    """
    Handles writing AERIS-TWIN telemetry data to InfluxDB.
    """

    def __init__(self):

        # Load environment variables from .env
        load_dotenv()

        self.url = os.getenv("INFLUXDB_URL")
        self.token = os.getenv("INFLUXDB_TOKEN")
        self.org = os.getenv("INFLUXDB_ORG")
        self.bucket = os.getenv("INFLUXDB_BUCKET")

        self._retry_after = 0.0
        self._connection_error_reported = False
        self._retry_delay_seconds = 30.0
        self.fallback_path = Path(__file__).resolve().parents[1] / "data" / "flight_history_fallback.json"
        
        self.available = all([self.url, self.token, self.org, self.bucket])
        if self.available:
            # Connect to InfluxDB
            self.client = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org,
                timeout=500,
                retries=0,
            )
            self.write_api = self.client.write_api(write_options=ASYNCHRONOUS)
            self.query_api = self.client.query_api()
            print("InfluxDB writer initialized successfully.")
        else:
            self.client = None
            self.write_api = None
            self.query_api = None
            print("InfluxDB configuration missing. Running in fallback mode.")

    def _can_attempt_write(self):
        return self.available and time.monotonic() >= self._retry_after

    def _record_write_success(self):
        self._retry_after = 0.0
        self._connection_error_reported = False

    def _record_write_failure(self, exc):
        self._retry_after = time.monotonic() + self._retry_delay_seconds
        if self._connection_error_reported:
            return False
        self._connection_error_reported = True
        return str(exc)

    def _load_fallback(self):
        try:
            with self.fallback_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return {
                "flights": data.get("flights", {}),
                "telemetry": data.get("telemetry", {}),
            }
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {"flights": {}, "telemetry": {}}

    def _save_fallback(self, data):
        self.fallback_path.parent.mkdir(parents=True, exist_ok=True)
        with self.fallback_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

    def _save_fallback_telemetry(self, flight_id, telemetry):
        if not flight_id:
            return
        data = self._load_fallback()
        points = data["telemetry"].setdefault(str(flight_id), [])
        point = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **{key: float(value) for key, value in telemetry.items() if isinstance(value, (int, float))},
        }
        points.append(point)
        data["telemetry"][str(flight_id)] = points[-1200:]
        self._save_fallback(data)

    def _save_fallback_flight(self, flight_id, mission_name, mission_key, flight_status, start_time, end_time, duration_seconds, statistics):
        data = self._load_fallback()
        data["flights"][str(flight_id)] = {
            "flight_id": str(flight_id),
            "mission_name": mission_name or "unknown",
            "mission_key": mission_key or "unknown",
            "status": flight_status or "COMPLETED",
            "start_time": float(start_time.timestamp()) if hasattr(start_time, "timestamp") else float(start_time or 0.0),
            "end_time": float(end_time.timestamp()) if hasattr(end_time, "timestamp") else float(end_time or 0.0),
            "duration_seconds": float(duration_seconds or 0.0),
            "max_altitude_m": float(statistics.get("max_altitude_m", 0.0) or 0.0),
            "max_rpm": float(statistics.get("max_rpm", 0.0) or 0.0),
            "max_cht_c": float(statistics.get("max_cht_c", 0.0) or 0.0),
            "max_egt_c": float(statistics.get("max_egt_c", 0.0) or 0.0),
            "max_vibration_rms": float(statistics.get("max_vibration_rms", 0.0) or 0.0),
            "minimum_health_score": float(statistics.get("minimum_health_score", 100.0) or 100.0),
            "final_health_score": float(statistics.get("final_health_score", 100.0) or 100.0),
            "fault_detected": bool(statistics.get("fault_detected", False)),
            "fault_type": str(statistics.get("fault_type", "NORMAL") or "NORMAL"),
            "fault_first_seen": float(statistics.get("fault_first_seen") or 0.0),
            "fault_last_seen": float(statistics.get("fault_last_seen") or 0.0),
            "fault_event_count": int(statistics.get("fault_event_count", 0) or 0),
            "mission_progress": float(statistics.get("mission_progress", 0.0) or 0.0),
            "telemetry_points": int(statistics.get("telemetry_points", 0) or 0),
        }
        self._save_fallback(data)

    def write_telemetry(self, telemetry: dict, flight_id=None, mission_name=None):
        """
        Write sensor telemetry to InfluxDB.
        """

        if not self._can_attempt_write():
            self._save_fallback_telemetry(flight_id, telemetry)
            return False

        point = Point("engine_telemetry")
        if flight_id:
            point = point.tag("flight_id", str(flight_id))
        if mission_name:
            point = point.tag("mission_name", str(mission_name))

        # Add all numeric telemetry values as fields
        for key, value in telemetry.items():
            if isinstance(value, (int, float)):
                point = point.field(key, float(value))

        # Use real UTC time for database storage
        point = point.time(
            datetime.now(timezone.utc),
            WritePrecision.NS,
        )

        try:
            self.write_api.write(
                bucket=self.bucket,
                org=self.org,
                record=point,
            )
        except Exception as exc:
            self._save_fallback_telemetry(flight_id, telemetry)
            return self._record_write_failure(exc)
        self._record_write_success()
        return True

    def write_flight_record(
        self,
        flight_id,
        mission_name,
        mission_key,
        flight_status,
        start_time,
        end_time,
        duration_seconds,
        statistics,
    ):
        """
        Write a summarized flight record to InfluxDB.
        """
        point = (
            Point("flight_records")
            .tag("flight_id", str(flight_id))
            .tag("mission_name", str(mission_name or "unknown"))
            .tag("mission_key", str(mission_key or "unknown"))
            .tag("flight_status", str(flight_status or "COMPLETED"))
            .field("start_time", float(start_time.timestamp()) if hasattr(start_time, "timestamp") else float(start_time or 0.0))
            .field("end_time", float(end_time.timestamp()) if hasattr(end_time, "timestamp") else float(end_time or 0.0))
            .field("duration_seconds", float(duration_seconds or 0.0))
            .field("max_altitude_m", float(statistics.get("max_altitude_m", 0.0) or 0.0))
            .field("max_rpm", float(statistics.get("max_rpm", 0.0) or 0.0))
            .field("max_cht_c", float(statistics.get("max_cht_c", 0.0) or 0.0))
            .field("max_egt_c", float(statistics.get("max_egt_c", 0.0) or 0.0))
            .field("max_vibration_rms", float(statistics.get("max_vibration_rms", 0.0) or 0.0))
            .field("minimum_health_score", float(statistics.get("minimum_health_score", 100.0) or 100.0))
            .field("final_health_score", float(statistics.get("final_health_score", 100.0) or 100.0))
            .field("fault_detected", bool(statistics.get("fault_detected", False)))
            .field("fault_type", str(statistics.get("fault_type", "NORMAL") or "NORMAL"))
            .field("fault_first_seen", float(statistics.get("fault_first_seen") or 0.0))
            .field("fault_last_seen", float(statistics.get("fault_last_seen") or 0.0))
            .field("fault_event_count", int(statistics.get("fault_event_count", 0) or 0))
            .field("mission_progress", float(statistics.get("mission_progress", 0.0) or 0.0))
            .field("telemetry_points", int(statistics.get("telemetry_points", 0) or 0))
            .time(
                datetime.now(timezone.utc),
                WritePrecision.NS,
            )
        )
        if not self._can_attempt_write():
            self._save_fallback_flight(flight_id, mission_name, mission_key, flight_status, start_time, end_time, duration_seconds, statistics)
            return False
        try:
            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
        except Exception as exc:
            self._save_fallback_flight(flight_id, mission_name, mission_key, flight_status, start_time, end_time, duration_seconds, statistics)
            return self._record_write_failure(exc)
        self._record_write_success()
        return True

    def get_flights(self, limit=50):
        """Return recent flight summaries from the flight_records measurement."""
        fallback = self._load_fallback()
        if fallback["flights"] and self._connection_error_reported:
            return sorted(
                fallback["flights"].values(),
                key=lambda flight: float(flight.get("start_time") or 0.0),
                reverse=True,
            )[:int(limit)]
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -30d)
          |> filter(fn: (r) => r._measurement == "flight_records")
                    |> pivot(rowKey:["_time", "flight_id"], columnKey:["_field"], valueColumn:"_value")
          |> sort(desc: true)
          |> limit(n: {int(limit)})
        '''
        try:
            result = self.query_api.query(org=self.org, query=query)
        except Exception:
            result = []

        merged_flights = {str(key): value for key, value in fallback["flights"].items()}
        for table in result:
            for record in table.records:
                values = dict(record.values)
                flight_id = values.get("flight_id")
                if not flight_id:
                    continue
                flight_id = str(flight_id)
                flight = merged_flights.setdefault(flight_id, {
                    "flight_id": str(flight_id),
                    "mission_name": values.get("mission_name", "UNKNOWN"),
                    "mission_key": values.get("mission_key", "unknown"),
                    "status": values.get("flight_status", "COMPLETED"),
                    "start_time": values.get("start_time"),
                    "end_time": values.get("end_time"),
                    "duration_seconds": float(values.get("duration_seconds", 0.0) or 0.0),
                    "max_altitude_m": float(values.get("max_altitude_m", 0.0) or 0.0),
                    "max_rpm": float(values.get("max_rpm", 0.0) or 0.0),
                    "max_cht_c": float(values.get("max_cht_c", 0.0) or 0.0),
                    "max_egt_c": float(values.get("max_egt_c", 0.0) or 0.0),
                    "max_vibration_rms": float(values.get("max_vibration_rms", 0.0) or 0.0),
                    "minimum_health_score": float(values.get("minimum_health_score", 100.0) or 100.0),
                    "fault_detected": bool(values.get("fault_detected", False)),
                    "fault_type": values.get("fault_type", "NORMAL"),
                    "fault_first_seen": float(values.get("fault_first_seen", 0.0) or 0.0),
                    "fault_last_seen": float(values.get("fault_last_seen", 0.0) or 0.0),
                    "fault_event_count": int(values.get("fault_event_count", 0) or 0),
                    "telemetry_points": int(values.get("telemetry_points", 0) or 0),
                })
                for key in (
                    "mission_name", "mission_key", "status", "start_time", "end_time",
                    "duration_seconds", "max_altitude_m", "max_rpm", "max_cht_c",
                    "max_egt_c", "max_vibration_rms", "minimum_health_score",
                    "fault_detected", "fault_type", "fault_first_seen", "fault_last_seen",
                    "fault_event_count", "telemetry_points",
                ):
                    if key in values and values[key] is not None:
                        flight[key] = values[key]
        return sorted(
            merged_flights.values(),
            key=lambda flight: float(flight.get("start_time") or 0.0),
            reverse=True,
        )[:int(limit)]

    def get_flight_by_id(self, flight_id):
        fallback = self._load_fallback()["flights"].get(str(flight_id))
        if fallback:
            return fallback
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -30d)
          |> filter(fn: (r) => r._measurement == "flight_records" and r.flight_id == "{flight_id}")
                    |> pivot(rowKey:["_time", "flight_id"], columnKey:["_field"], valueColumn:"_value")
          |> sort(desc: true)
          |> limit(n: 1)
        '''
        try:
            result = self.query_api.query(org=self.org, query=query)
        except Exception:
            result = []
        merged_values = {}
        for table in result:
            for record in table.records:
                values = dict(record.values)
                if values:
                    merged_values.update({key: value for key, value in values.items() if value is not None})
        if not merged_values:
            return fallback
        return {
            "flight_id": str(merged_values.get("flight_id", flight_id)),
            "mission_name": merged_values.get("mission_name", "UNKNOWN"),
            "mission_key": merged_values.get("mission_key", "unknown"),
            "status": merged_values.get("flight_status", "COMPLETED"),
            "start_time": merged_values.get("start_time"),
            "end_time": merged_values.get("end_time"),
            "duration_seconds": float(merged_values.get("duration_seconds", 0.0) or 0.0),
            "max_altitude_m": float(merged_values.get("max_altitude_m", 0.0) or 0.0),
            "max_rpm": float(merged_values.get("max_rpm", 0.0) or 0.0),
            "max_cht_c": float(merged_values.get("max_cht_c", 0.0) or 0.0),
            "max_egt_c": float(merged_values.get("max_egt_c", 0.0) or 0.0),
            "max_vibration_rms": float(merged_values.get("max_vibration_rms", 0.0) or 0.0),
            "minimum_health_score": float(merged_values.get("minimum_health_score", 100.0) or 100.0),
            "final_health_score": float(merged_values.get("final_health_score", 100.0) or 100.0),
            "fault_detected": bool(merged_values.get("fault_detected", False)),
            "fault_type": merged_values.get("fault_type", "NORMAL"),
            "fault_first_seen": float(merged_values.get("fault_first_seen", 0.0) or 0.0),
            "fault_last_seen": float(merged_values.get("fault_last_seen", 0.0) or 0.0),
            "fault_event_count": int(merged_values.get("fault_event_count", 0) or 0),
            "mission_progress": float(merged_values.get("mission_progress", 0.0) or 0.0),
            "telemetry_points": int(merged_values.get("telemetry_points", 0) or 0),
        }

    def get_flight_telemetry(self, flight_id, limit=1200):
        fallback_points = self._load_fallback()["telemetry"].get(str(flight_id), [])
        if fallback_points:
            points = [{
                "timestamp": point.get("timestamp", ""),
                "rpm": float(point.get("rpm", 0.0) or 0.0),
                "cht_c": max(float(point.get(f"cht_cylinder_{index}_c", 0.0) or 0.0) for index in range(1, 5)),
                "egt_c": max(float(point.get(f"egt_cylinder_{index}_c", 0.0) or 0.0) for index in range(1, 5)),
                "oil_temperature_c": float(point.get("oil_temperature_c", 0.0) or 0.0),
                "oil_pressure_psi": float(point.get("oil_pressure_psi", 0.0) or 0.0),
                "vibration_rms": float(point.get("vibration_rms", 0.0) or 0.0),
            } for point in fallback_points]
            return points[-int(limit):]
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -30d)
          |> filter(fn: (r) => r._measurement == "engine_telemetry" and r.flight_id == "{flight_id}")
          |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")
          |> sort(desc: false)
          |> limit(n: {int(limit)})
        '''
        try:
            result = self.query_api.query(org=self.org, query=query)
        except Exception:
            result = []

        points = []
        for table in result:
            for record in table.records:
                values = dict(record.values)
                if not values:
                    continue
                if "_time" in values:
                    timestamp = values.get("_time")
                else:
                    timestamp = record.get_time()
                telemetry = {
                    "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
                    "rpm": float(values.get("rpm", 0.0) or 0.0),
                    "cht_c": max(float(values.get("cht_cylinder_1_c", 0.0) or 0.0), float(values.get("cht_cylinder_2_c", 0.0) or 0.0), float(values.get("cht_cylinder_3_c", 0.0) or 0.0), float(values.get("cht_cylinder_4_c", 0.0) or 0.0)),
                    "egt_c": max(float(values.get("egt_cylinder_1_c", 0.0) or 0.0), float(values.get("egt_cylinder_2_c", 0.0) or 0.0), float(values.get("egt_cylinder_3_c", 0.0) or 0.0), float(values.get("egt_cylinder_4_c", 0.0) or 0.0)),
                    "oil_temperature_c": float(values.get("oil_temperature_c", 0.0) or 0.0),
                    "oil_pressure_psi": float(values.get("oil_pressure_psi", 0.0) or 0.0),
                    "vibration_rms": float(values.get("vibration_rms", 0.0) or 0.0),
                }
                points.append(telemetry)
        if not points:
            points = [{
                "timestamp": point.get("timestamp", ""),
                "rpm": float(point.get("rpm", 0.0) or 0.0),
                "cht_c": max(float(point.get(f"cht_cylinder_{index}_c", 0.0) or 0.0) for index in range(1, 5)),
                "egt_c": max(float(point.get(f"egt_cylinder_{index}_c", 0.0) or 0.0) for index in range(1, 5)),
                "oil_temperature_c": float(point.get("oil_temperature_c", 0.0) or 0.0),
                "oil_pressure_psi": float(point.get("oil_pressure_psi", 0.0) or 0.0),
                "vibration_rms": float(point.get("vibration_rms", 0.0) or 0.0),
            } for point in fallback_points]
        if len(points) > 1200:
            step = max(1, len(points) // 1200)
            points = points[::step]
        return points

    def close(self):
        """
        Close the InfluxDB connection safely.
        """

        if self.client:
            self.client.close()
