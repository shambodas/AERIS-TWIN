"""LAN-capable web adapter for the authoritative AERIS-TWIN simulator."""

from __future__ import annotations

import csv
import json
import math
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


from database.influx_writer import InfluxWriter
from simulation.engine_simulator import EngineInputs, EngineSimulator
from simulation.mission import MissionProfile
from telemetry.mqtt import MQTTConfig, MQTTPublisher
from intelligence.pipeline import IntelligencePipeline


ROOT = Path(__file__).parent
WEB_ROOT = ROOT / "web"
HOST = os.getenv("AERIS_HOST", "0.0.0.0")
PORT = int(os.getenv("AERIS_PORT", "8080"))
TICK_SECONDS = 0.1
MAX_HISTORY = 600
UAV_ROUTE_TIME_SCALE = 150.0
MISSION_NAMES = {
    "cruise_isr": "Cruise ISR",
    "high_altitude": "High Altitude",
    "long_endurance": "Long Endurance",
    "hot_weather": "Hot Weather",
    "rapid_throttle": "Rapid Throttle",
}
MISSION_LOCATIONS = {
    "Delhi": {"lat": 28.6139, "lng": 77.2090},
    "Jaipur": {"lat": 26.9124, "lng": 75.7873},
    "Jodhpur": {"lat": 26.2389, "lng": 73.0243},
    "Ahmedabad": {"lat": 23.0225, "lng": 72.5714},
    "Mumbai": {"lat": 19.0760, "lng": 72.8777},
    "Hyderabad": {"lat": 17.3850, "lng": 78.4867},
    "Bengaluru": {"lat": 12.9716, "lng": 77.5946},
    "Mysuru": {"lat": 12.2958, "lng": 76.6394},
    "Chennai": {"lat": 13.0827, "lng": 80.2707},
    "Nagpur": {"lat": 21.1458, "lng": 79.0882},
    "Pune": {"lat": 18.5204, "lng": 73.8567},
    "Bhopal": {"lat": 23.2599, "lng": 77.4126},
}


class TwinController:
    def __init__(self):
        self.lock = threading.RLock()
        self.simulator = EngineSimulator(timestep_s=TICK_SECONDS, random_seed=42)
        self.mission = MissionProfile()
        self.running = False
        self.paused = False
        self.flight_state = "READY"
        self.mission_name = "cruise_isr"
        self.mission_base = "Delhi"
        self.mission_route = []
        self.mission_status = "READY"
        self.mission_risk = {"level": "CLEAR", "recommended_return": False, "message": "MISSION STABLE"}
        self.altitude_override = None
        self.speed_override = None
        self.heading = 45.0
        self.position = dict(MISSION_LOCATIONS["Delhi"])
        self.waypoints = []
        self.route_waypoints = []
        self.following_path = False
        self.active_fault_name = ""
        self.history = deque(maxlen=MAX_HISTORY)
        self.events = deque(maxlen=40)
        self.clients = []
        self.mqtt = self._make_mqtt()
        self.influx_writer = InfluxWriter()
        self.intelligence = IntelligencePipeline()
        self.current_flight_id = None
        self.flight_start_time = None
        self.flight_active = False
        self.flight_record_finalized = False
        self.flight_statistics = self._new_flight_statistics()
        self.last_state = None
        self._reset_locked()

    @staticmethod
    def _new_flight_statistics():
        return {
            "max_altitude_m": 0.0,
            "max_rpm": 0.0,
            "max_cht_c": 0.0,
            "max_egt_c": 0.0,
            "max_vibration_rms": 0.0,
            "minimum_health_score": 100.0,
            "final_health_score": 100.0,
            "fault_detected": False,
            "fault_type": "NORMAL",
            "fault_first_seen": None,
            "fault_last_seen": None,
            "fault_event_count": 0,
            "mission_progress": 0.0,
            "telemetry_points": 0,
        }

    def _start_flight_session_locked(self):
        if self.flight_active and self.current_flight_id:
            return
        self.current_flight_id = f"aeris-{uuid.uuid4().hex[:8]}"
        self.flight_start_time = datetime.now(timezone.utc)
        self.flight_active = True
        self.flight_record_finalized = False
        self.flight_statistics = self._new_flight_statistics()
        self.intelligence.reset_rul_state()
        self.events.appendleft({"kind": "flight", "message": f"FLIGHT SESSION STARTED: {self.current_flight_id}"})

    def _update_flight_statistics_locked(self, measured, intelligence, altitude_m, fault_type, mission_progress):
        if not self.flight_active or not self.current_flight_id:
            return
        health = float(intelligence.get("health", {}).get("score", 100.0) or 100.0)
        self.flight_statistics["max_altitude_m"] = max(self.flight_statistics.get("max_altitude_m", 0.0), float(altitude_m or 0.0))
        self.flight_statistics["max_rpm"] = max(self.flight_statistics.get("max_rpm", 0.0), float(measured.get("rpm", 0.0) or 0.0))
        cht = max(float(measured.get("cht_cylinder_1_c", 0.0) or 0.0), float(measured.get("cht_cylinder_2_c", 0.0) or 0.0), float(measured.get("cht_cylinder_3_c", 0.0) or 0.0), float(measured.get("cht_cylinder_4_c", 0.0) or 0.0))
        egt = max(float(measured.get("egt_cylinder_1_c", 0.0) or 0.0), float(measured.get("egt_cylinder_2_c", 0.0) or 0.0), float(measured.get("egt_cylinder_3_c", 0.0) or 0.0), float(measured.get("egt_cylinder_4_c", 0.0) or 0.0))
        self.flight_statistics["max_cht_c"] = max(self.flight_statistics.get("max_cht_c", 0.0), cht)
        self.flight_statistics["max_egt_c"] = max(self.flight_statistics.get("max_egt_c", 0.0), egt)
        self.flight_statistics["max_vibration_rms"] = max(self.flight_statistics.get("max_vibration_rms", 0.0), float(measured.get("vibration_rms", 0.0) or 0.0))
        self.flight_statistics["minimum_health_score"] = min(self.flight_statistics.get("minimum_health_score", 100.0), health)
        self.flight_statistics["final_health_score"] = health
        self.flight_statistics["mission_progress"] = max(self.flight_statistics.get("mission_progress", 0.0), float(mission_progress or 0.0))
        self.flight_statistics["telemetry_points"] = int(self.flight_statistics.get("telemetry_points", 0) + 1)
        normalized_fault = str(fault_type or "NORMAL").upper()
        if normalized_fault != "NORMAL":
            fault_time = datetime.now(timezone.utc).timestamp()
            self.flight_statistics["fault_detected"] = True
            self.flight_statistics["fault_type"] = normalized_fault
            self.flight_statistics["fault_first_seen"] = self.flight_statistics.get("fault_first_seen") or fault_time
            self.flight_statistics["fault_last_seen"] = fault_time
            self.flight_statistics["fault_event_count"] = int(self.flight_statistics.get("fault_event_count", 0)) + 1

    def _finalize_flight_locked(self, status="COMPLETED"):
        if not self.flight_active or not self.current_flight_id or self.flight_record_finalized:
            return
        flight_id = self.current_flight_id
        flight_status = (status or "COMPLETED").upper()
        end_time = datetime.now(timezone.utc)
        start_time = self.flight_start_time or end_time
        duration_seconds = max(0.0, (end_time - start_time).total_seconds())
        stats = self.flight_statistics.copy()
        if stats.get("max_altitude_m", 0.0) <= 0.0:
            stats["max_altitude_m"] = 0.0
        try:
            self.influx_writer.write_flight_record(
                flight_id=flight_id,
                mission_name=MISSION_NAMES.get(self.mission_name, self.mission_name),
                mission_key=self.mission_name,
                flight_status=flight_status,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration_seconds,
                statistics=stats,
            )
        except Exception as exc:
            self.events.appendleft({"kind": "warning", "message": f"Flight summary write failed: {exc}"})
        self.flight_record_finalized = True
        self.events.appendleft({"kind": "flight", "message": f"FLIGHT CLOSED: {flight_id} ({flight_status})"})
        self.current_flight_id = None
        self.flight_start_time = None
        self.flight_active = False
        self.flight_statistics = self._new_flight_statistics()
        self.intelligence.reset_rul_state()

    def _make_mqtt(self):
        enabled = os.getenv("AERIS_MQTT", "0").lower() in {"1", "true", "yes"}
        publisher = MQTTPublisher(MQTTConfig(
            broker_host=os.getenv("AERIS_MQTT_HOST", "localhost"),
            broker_port=int(os.getenv("AERIS_MQTT_PORT", "1883")),
            topic_prefix=os.getenv("AERIS_MQTT_PREFIX", "aeris-twin"),
            client_id="aeris-twin-dashboard-adapter",
        ), simulation_mode=not enabled)
        if enabled:
            try:
                publisher.connect()
            except Exception as exc:
                self.events.appendleft({"kind": "warning", "message": f"MQTT unavailable: {exc}"})
        return publisher

    def _reset_locked(self):
        self.simulator.reset()
        self.running = False
        self.paused = False
        self.flight_state = "READY"
        self.mission_base = "Delhi"
        self.mission_route = []
        self.mission_status = "READY"
        self.mission_risk = {"level": "CLEAR", "recommended_return": False, "message": "MISSION STABLE"}
        self.altitude_override = None
        self.speed_override = None
        self.heading = 45.0
        self.position = dict(MISSION_LOCATIONS["Delhi"])
        self.waypoints.clear()
        self.route_waypoints.clear()
        self.following_path = False
        self.active_fault_name = ""
        self.history.clear()
        self.current_flight_id = None
        self.flight_start_time = None
        self.flight_active = False
        self.flight_record_finalized = False
        self.flight_statistics = self._new_flight_statistics()
        self.intelligence.reset_history()
        self.intelligence.reset_rul_state()
        self.intelligence.invalidate_cache()
        self.events.appendleft({"kind": "info", "message": "Simulation reset"})
        self._sample_locked()
        self.last_state["digital_twin"]["simulation_time_s"] = 0.0
        self.last_state["mission"]["elapsed_s"] = 0.0

    def _normalize_route(self, route):
        if not isinstance(route, list) or not route:
            raise ValueError("Mission route must contain at least one location")
        normalized = []
        for location in route:
            if not isinstance(location, str):
                raise ValueError("Mission locations must be named cities")
            cleaned = location.strip()
            if cleaned not in MISSION_LOCATIONS:
                raise ValueError(f"Unsupported mission location: {cleaned}")
            if cleaned not in normalized:
                normalized.append(cleaned)
        if len(normalized) < 2:
            raise ValueError("Mission route must include a start and destination")
        return normalized

    def _route_waypoints(self, route):
        return [{"lat": MISSION_LOCATIONS[name]["lat"], "lng": MISSION_LOCATIONS[name]["lng"]} for name in route]

    def _set_route_locked(self, route, *, place_at_start=False):
        route = self._normalize_route(route)
        self.mission_base = route[0]
        self.mission_route = list(route)
        start = MISSION_LOCATIONS[route[0]]
        if place_at_start:
            self.position = {"lat": start["lat"], "lng": start["lng"]}
        self.route_waypoints = self._route_waypoints(route)
        self.waypoints = self._route_waypoints(route[1:])
        self.following_path = bool(self.waypoints)
        return route

    def _mission_risk_locked(self, current_intelligence=None):
        if self.mission_status == "RETURNING":
            return {"level": "RETURNING", "recommended_return": False, "message": "RETURNING TO BASE"}
        
        severity = "NORMAL"
        health = 100.0
        
        if current_intelligence:
            severity = str(current_intelligence.get("severity", "NORMAL")).upper()
            health = float(current_intelligence.get("health", {}).get("score", 100.0))
        else:
            state = self.last_state or {}
            digital = state.get("digital_twin", {}) if isinstance(state, dict) else {}
            severity = str(digital.get("ai_severity", "NORMAL") or "NORMAL").upper()
            health = float(digital.get("health_pct", 100.0) or 100.0)

        if severity in {"CRITICAL", "SEVERE"} or health <= 35.0:
            return {"level": "AT_RISK", "recommended_return": True, "message": "RETURN TO BASE RECOMMENDED"}
        if severity == "WARNING" or health <= 55.0:
            return {"level": "MONITOR", "recommended_return": False, "message": "ENGINE CONDITION REQUIRES WATCH"}
        return {"level": "CLEAR", "recommended_return": False, "message": "MISSION STABLE"}

    def _mission_input_locked(self):
        state = self.mission.state_at(self.simulator.time_s)
        inputs = self.mission.engine_inputs_at(self.simulator.time_s)
        if self.mission_name == "high_altitude":
            inputs.altitude_m = max(inputs.altitude_m, 8000.0)
        elif self.mission_name == "hot_weather":
            # Simulate a +20 K ISA deviation (approx. 45 °C day at sea level)
            # so the atmosphere model raises ambient temperature, reducing air
            # density AND elevating the baseline CHT / oil temperature.
            inputs.temperature_offset_k = 20.0
        elif self.mission_name == "long_endurance":
            inputs.throttle_pct = min(inputs.throttle_pct, 62.0)
        elif self.mission_name == "rapid_throttle":
            inputs.throttle_pct = 35.0 if int(self.simulator.time_s * 0.5) % 2 else 90.0
        if self.altitude_override is not None:
            inputs.altitude_m = self.altitude_override
        if self.speed_override is not None:
            inputs.airspeed_mps = self.speed_override
        return state, inputs

    def _sample_locked(self):
        if self.last_state is None:
            _, inputs = self._mission_input_locked()
            true_state, sensor_state = self.simulator.step(inputs)
        else:
            _, inputs = self._mission_input_locked()
            true_state, sensor_state = self.simulator.step(inputs)
        mission_state = self.mission.state_at(true_state.time_s)
        fault = true_state.fault_type
        thermal = max(true_state.cht_c) if true_state.cht_c else 0.0
        measured = asdict(sensor_state)

        if fault == "ENGINE_FAILURE" and self.flight_state == "FLYING":
            self.events.appendleft({"kind": "critical", "message": "ENGINE FAILURE DETECTED: END OF LIFE"})
            self._start_flight_session_locked()
            try:
                self.influx_writer.write_telemetry(
                    measured,
                    flight_id=self.current_flight_id,
                    mission_name=MISSION_NAMES.get(self.mission_name, self.mission_name),
                )
            except Exception as exc:
                self.events.appendleft({"kind": "warning", "message": f"Final telemetry write failed: {exc}"})
            
            self._update_flight_statistics_locked(
                measured,
                {"health": {"score": 0.0}, "severity": "SEVERE"},
                true_state.altitude_m,
                "ENGINE_FAILURE",
                mission_state.mission_progress,
            )
            self._finalize_flight_locked("FAILED")
            self.running = False
            self.flight_state = "FAILED"

        elif self.running and not self.paused and self.flight_state == "FLYING":
            self._start_flight_session_locked()
            try:
                res = self.influx_writer.write_telemetry(
                    measured,
                    flight_id=self.current_flight_id,
                    mission_name=MISSION_NAMES.get(self.mission_name, self.mission_name),
                )
                if isinstance(res, str):
                    raise ConnectionError(res)
            except Exception as exc:
                self.events.appendleft({
                    "kind": "warning",
                    "message": f"Telemetry persistence unavailable — live simulation continues."
                })

        intelligence = self.intelligence.process(true_state, sensor_state, timestamp=true_state.time_s)
        if self.flight_state == "READY" and not self.active_fault_name:
            intelligence["health"]["score"] = 100.0
            intelligence["severity"] = "NORMAL"
            intelligence["fault_classification"]["fault_type"] = "NORMAL"
            intelligence["fault_classification"]["confidence"] = 1.0
            intelligence["fault_classification"]["probabilities"] = {"NORMAL": 1.0}
            if "diagnosis" not in intelligence:
                intelligence["diagnosis"] = {}
            intelligence["diagnosis"]["fault_type"] = "NORMAL"
            intelligence["diagnosis"]["title"] = "NORMAL ENGINE OPERATION"
            intelligence["diagnosis"]["interpretation"] = "AERIS-TWIN is performing preflight checks. Sensor data is nominal."
            intelligence["diagnosis"]["recommended_action"] = "System ready for mission start."
        health = float(intelligence["health"]["score"])
        status = {"NORMAL": "HEALTHY", "INFORMATION": "HEALTHY", "WARNING": "WARNING", "CRITICAL": "CRITICAL", "SEVERE": "CRITICAL"}.get(intelligence["severity"], "WARNING")
        if self.flight_active and self.current_flight_id:
            self._update_flight_statistics_locked(
                measured,
                intelligence,
                true_state.altitude_m,
                intelligence.get("fault_classification", {}).get("fault_type", fault),
                mission_state.mission_progress,
            )
        self.mission_risk = self._mission_risk_locked(intelligence)
        mission_risk = self.mission_risk
        distance_to_next_km = 0.0
        if self.following_path and self.waypoints:
            target = self.waypoints[0]
            delta_lat = target["lat"] - self.position["lat"]
            delta_lng = target["lng"] - self.position["lng"]
            distance_to_next_km = math.hypot(
                delta_lat * 111111.0,
                delta_lng * 111111.0 * math.cos(math.radians(self.position["lat"]))
            ) / 1000.0

        mission_progress = mission_state.mission_progress
        if self.mission_status == "RETURNING" and hasattr(self, 'rtb_initial_distance'):
            if self.waypoints:
                dist = distance_to_next_km * 1000.0
                mission_progress = max(0.0, min(1.0, 1.0 - (dist / max(1.0, self.rtb_initial_distance))))
            else:
                mission_progress = 1.0
        elif self.mission_status == "RECOVERED":
            mission_progress = 1.0

        payload = {
            "timestamp": time.time(), "uav": {"status": self.flight_state, "altitude_m": true_state.altitude_m, "speed_mps": true_state.airspeed_mps, "heading": self.heading, "progress": mission_progress, "position": dict(self.position), "distance_to_next_km": distance_to_next_km},
            "flight_path": {"waypoints": list(self.waypoints), "route": list(self.route_waypoints), "following": self.following_path},
            "engine": {"status": status, "rpm": measured["rpm"], "cht_c": max(measured["cht_cylinder_1_c"], measured["cht_cylinder_2_c"], measured["cht_cylinder_3_c"], measured["cht_cylinder_4_c"]), "egt_c": max(measured["egt_cylinder_1_c"], measured["egt_cylinder_2_c"], measured["egt_cylinder_3_c"], measured["egt_cylinder_4_c"]), "oil_temperature_c": measured["oil_temperature_c"], "oil_pressure_psi": measured["oil_pressure_psi"], "vibration_rms": measured["vibration_rms"], "fuel_flow_kg_s": measured["fuel_flow_kg_s"], "throttle_pct": true_state.throttle_pct, "load_pct": min(100.0, max(0.0, true_state.power_kw / 0.25)), "torque_nm": measured["torque_nm"], "intake_pressure_kpa": measured["manifold_pressure_kpa"], "battery_voltage_v": true_state.battery_voltage_v, "battery_soc": true_state.battery_soc, "battery_current_a": true_state.battery_current_a, "alternator_power_w": true_state.alternator_power_w, "injection_timing_nominal_deg": true_state.injection_timing_nominal_deg, "injection_timing_actual_deg": true_state.injection_timing_actual_deg, "injection_timing_deviation_deg": true_state.injection_timing_deviation_deg},
            "digital_twin": {"status": "SYNCHRONIZED", "telemetry_rate_hz": round(1 / self.simulator.dt, 1), "simulation_time_s": true_state.time_s, "health_pct": round(health, 1), "fault": fault, "active_fault_name": self.active_fault_name, "fault_severity": true_state.fault_severity, "ai_health": intelligence["health"]["score"], "ai_severity": intelligence["severity"], "ai_fault": intelligence["fault_classification"]["fault_type"], "ai_confidence": intelligence["fault_classification"]["confidence"], "intelligence_mode": self.intelligence.runtime_mode},
            "mission": {"id": "AT-001", "name": MISSION_NAMES.get(self.mission_name, "Cruise ISR"), "key": self.mission_name, "phase": mission_state.phase.value, "progress": mission_progress, "elapsed_s": true_state.time_s, "running": self.running, "paused": self.paused, "status": self.mission_status, "route": list(self.mission_route), "base": self.mission_base, "risk_level": mission_risk["level"], "return_recommended": mission_risk["recommended_return"], "risk_message": mission_risk["message"]},
            "telemetry_status": "LIVE" if self.running and not self.paused else "PAUSED" if self.paused else "STOPPED" if self.flight_state == "STOPPED" else "READY",
            "alerts": self._alerts(status, fault, thermal, measured["oil_pressure_psi"], measured["vibration_rms"]),
            "telemetry": measured,
            "intelligence": intelligence,
            "events": list(self.events),
        }
        self.last_state = payload
        self.history.append({"time_s": true_state.time_s, **payload["engine"], "status": status, "fault": fault})
        if self.mqtt.connected:
            try:
                self.mqtt.publish_engine_telemetry(sensor_state, mission_state.phase.value, true_state.time_s)
            except Exception:
                pass

    @staticmethod
    def _alerts(status, fault, temperature, oil_pressure, vibration):
        alerts = []
        if temperature >= 250: alerts.append({"id": "temp_critical", "level": "critical", "text": "CRITICAL ENGINE TEMPERATURE"})
        elif temperature >= 210: alerts.append({"id": "temp_warning", "level": "warning", "text": "HIGH ENGINE TEMPERATURE"})
        if oil_pressure < 20: alerts.append({"id": "oil_pressure_low", "level": "warning", "text": "LOW OIL PRESSURE"})
        if vibration > 1.0: alerts.append({"id": "vibration_high", "level": "warning", "text": "EXCESSIVE VIBRATION"})
        if fault != "NORMAL": alerts.append({"id": f"fault_{fault.lower()}", "level": "warning" if status != "CRITICAL" else "critical", "text": fault.replace("_", " ")})
        return alerts

    def tick(self):
        with self.lock:
            if self.running and not self.paused:
                self._advance_uav_locked()
                self._sample_locked()
            state = self.last_state
            for client in list(self.clients):
                try: client.send(state)
                except Exception:
                    self.clients.remove(client)


    def command(self, body):
        with self.lock:
            command = body.get("command")
            params = body.get("parameters", {})
            if command in {"start_uav", "start_flight"}:
                if params.get("altitude") is not None:
                    self.altitude_override = self._number(params.get("altitude"), 0.0, 12000.0)
                elif self.altitude_override is None:
                    self.altitude_override = 3500.0
                if params.get("speed") is not None:
                    self.speed_override = self._number(params.get("speed"), 0.0, 100.0)
                elif self.speed_override is None:
                    self.speed_override = 32.0
                if params.get("heading") is not None:
                    self.heading = self._number(params.get("heading"), 0.0, 359.0)
                self.running = True
                self.paused = False
                self.flight_state = "FLYING"
                self._start_flight_session_locked()
                
                # Fast-forward 120s of physics to reach thermal equilibrium.
                # This ensures the 408 validator queries a warm engine state where
                # the RF expectation models and candidate classifier are accurate,
                # and gives faults enough time to manifest their thermal signatures.
                ff_steps = int(120.0 / self.simulator.dt)
                for _ in range(ff_steps):
                    _, inputs = self._mission_input_locked()
                    self.simulator.step(inputs)
                self.intelligence.invalidate_cache()

                if self.mission_route:
                    self.mission_status = "IN_FLIGHT"
                if self.route_waypoints and self.waypoints:
                    self.following_path = True
            elif command == "start_mission":
                mission_name = params.get("mission", "cruise_isr")
                if mission_name not in MISSION_NAMES: raise ValueError("Unsupported mission")
                self.mission_name = mission_name; self.running = True; self.paused = False; self.flight_state = "FLYING"
                self._start_flight_session_locked()
                if self.altitude_override is None:
                    self.altitude_override = 3500.0
                if self.speed_override is None:
                    self.speed_override = 32.0
                # Enable wear accumulation only for long-endurance missions
                self.simulator.wear_rate_multiplier = 1.0 if mission_name == "long_endurance" else 0.0
                route = params.get("route")
                if route:
                    self._set_route_locked(route, place_at_start=True)
                elif not self.route_waypoints:
                    self._set_route_locked(self.mission_route or ["Delhi", "Jaipur", "Jodhpur"], place_at_start=True)
                elif self.route_waypoints and not self.running:
                    self.position = self.route_waypoints[0].copy()
                self.mission_status = "IN_FLIGHT"
                
                # Fast-forward 120s of physics to reach thermal equilibrium
                ff_steps = int(120.0 / self.simulator.dt)
                for _ in range(ff_steps):
                    _, inputs = self._mission_input_locked()
                    self.simulator.step(inputs)
                self.intelligence.invalidate_cache()
                
                route_desc = " → ".join(route) if route else "Custom Map Route"
                self.events.appendleft({"kind": "mission", "message": "MISSION STARTED: " + route_desc})
            elif command == "set_mission_route":
                route = self._set_route_locked(params.get("route", []), place_at_start=True)
                self.mission_status = "PLANNED"
                self.events.appendleft({"kind": "mission", "message": "MISSION PLANNED: " + " → ".join(route)})
            elif command == "return_to_base":
                if self.flight_state not in {"FLYING", "STOPPED", "PAUSED"}:
                    raise ValueError("RTB requires an active or stopped flight")
                base = MISSION_LOCATIONS.get(self.mission_base, MISSION_LOCATIONS["Delhi"])
                self.mission_status = "RETURNING"
                # Preserve self.mission_route for history
                delta_lat = base["lat"] - self.position["lat"]
                delta_lng = base["lng"] - self.position["lng"]
                self.rtb_initial_distance = math.hypot(
                    delta_lat * 111111.0,
                    delta_lng * 111111.0 * math.cos(math.radians(self.position["lat"]))
                )
                self.waypoints = [{"lat": base["lat"], "lng": base["lng"]}]
                self.route_waypoints = [dict(self.position), dict(base)]
                self.following_path = True
                self.running = True; self.paused = False; self.flight_state = "FLYING"
                self.events.appendleft({"kind": "mission", "message": "RETURNING TO BASE"})
            elif command in {"stop_uav", "stop_flight"}:
                self.running = False
                self.paused = False
                self.flight_state = "STOPPED"
                self.following_path = False
                if self.mission_status == "IN_FLIGHT":
                    self.mission_status = "STOPPED"
                self.mission_status = self.mission_status if self.mission_status not in {"READY", "PLANNED"} else "COMPLETED"
                self._finalize_flight_locked("STOPPED")
            elif command == "pause_uav":
                self.paused = not self.paused
                self.flight_state = "PAUSED" if self.paused else "FLYING"
            elif command in {"reset_simulation", "reset"}: self._reset_locked()
            elif command == "set_altitude": self.altitude_override = self._number(params.get("value", 0), 0.0, 12000.0)
            elif command == "set_speed": self.speed_override = self._number(params.get("value", 0), 0.0, 100.0)
            elif command == "set_heading": self.heading = self._number(params.get("value", 0), 0.0, 359.0)
            elif command == "set_waypoints":
                waypoints = params.get("waypoints", [])
                if not isinstance(waypoints, list) or len(waypoints) > 4:
                    raise ValueError("Provide up to four waypoints")
                selected = [{"lat": self._number(point.get("lat"), -90.0, 90.0), "lng": self._number(point.get("lng"), -180.0, 180.0)} for point in waypoints]
                self.route_waypoints = list(selected)
                if not self.running:
                    self.position = selected[0].copy() if selected else dict(self.position)
                self.waypoints = list(selected[1:]) if len(selected) > 1 else []
                self.following_path = bool(self.waypoints)
                self.mission_route = []
                self.mission_status = "PLANNED" if self.waypoints else "READY"
            elif command == "follow_path": self.following_path = bool(params.get("enabled", True)) and bool(self.waypoints)
            elif command in {"clear_path", "clear_waypoints"}:
                self.waypoints.clear()
                self.route_waypoints.clear()
                self.following_path = False
                self.mission_route = []
                self.mission_status = "READY"
            elif command == "set_throttle": raise ValueError("Throttle follows the selected MissionProfile and is not directly exposed")
            elif command == "fast_forward":
                # Advance the engine N simulated seconds without running the expensive
                # intelligence pipeline. Used by validation tooling to bring the engine
                # to a thermally stable state before injecting faults and querying AI.
                ff_seconds = float(params.get("seconds", 120.0))
                ff_steps = max(1, int(ff_seconds / self.simulator.dt))
                for _ in range(ff_steps):
                    _, inputs = self._mission_input_locked()
                    self.simulator.step(inputs)
                # Re-run a full sample (with fresh intelligence) after fast-forward.
                self.intelligence.invalidate_cache()
                self._sample_locked()
            elif command == "inject_fault": self._inject_fault(params.get("fault", ""), float(params.get("severity", 0.8)))
            elif command == "clear_fault":
                self.simulator.clear_faults()
                self.intelligence.reset_history()
                self.active_fault_name = ""
            else: raise ValueError("Unsupported command")
            self.mission_risk = self._mission_risk_locked()
            self.events.appendleft({"kind": "command", "message": f"{command.replace('_', ' ').title()} acknowledged"})
            if (self.running and not self.paused) or (command == "inject_fault" and not self.running):
                self._sample_locked()
            if self.last_state:
                self.last_state["uav"]["status"] = self.flight_state
                self.last_state["mission"]["running"] = self.running
                self.last_state["mission"]["paused"] = self.paused
                self.last_state["mission"]["status"] = self.mission_status
                self.last_state["mission"]["route"] = list(self.mission_route)
                self.last_state["mission"]["base"] = self.mission_base
                self.last_state["mission"]["risk_level"] = self.mission_risk["level"]
                self.last_state["mission"]["return_recommended"] = self.mission_risk["recommended_return"]
                self.last_state["mission"]["risk_message"] = self.mission_risk["message"]
                self.last_state["telemetry_status"] = "LIVE" if self.running and not self.paused else "PAUSED" if self.paused else "STOPPED" if self.flight_state == "STOPPED" else "READY"
                self.last_state["uav"]["position"] = dict(self.position)
                self.last_state["flight_path"] = {"waypoints": list(self.waypoints), "route": list(self.route_waypoints), "following": self.following_path}
                self.last_state["digital_twin"]["active_fault_name"] = self.active_fault_name
                self.last_state["events"] = list(self.events)
            return self.last_state

    def _advance_uav_locked(self):
        speed = float(self.last_state["uav"].get("speed_mps", 0.0)) if self.last_state else 0.0
        if speed <= 0.0:
            return
        if self.following_path and self.waypoints:
            target = self.waypoints[0]
            delta_lat = target["lat"] - self.position["lat"]
            delta_lng = target["lng"] - self.position["lng"]
            distance_m = math.hypot(
                delta_lat * 111111.0,
                delta_lng * 111111.0 * math.cos(math.radians(self.position["lat"]))
            )
            step_distance_m = speed * self.simulator.dt * UAV_ROUTE_TIME_SCALE
            self.heading = math.degrees(math.atan2(
                delta_lng * math.cos(math.radians(self.position["lat"])),
                delta_lat
            )) % 360.0
            if distance_m <= max(8.0, step_distance_m):
                self.position = target.copy()
                self.waypoints.pop(0)
                if self.mission_status == "RETURNING":
                    self.events.appendleft({"kind": "mission", "message": "✓ MISSION RECOVERED"})
                    self.mission_status = "RECOVERED"
                    self.following_path = False
                    self.running = False
                    self.flight_state = "READY"
                    self.waypoints.clear()
                    self.mission_route = []
                    self._finalize_flight_locked("RECOVERED")
                    return
                if self.mission_route:
                    reached = self.mission_route[1] if len(self.mission_route) > 1 else self.mission_route[0]
                    self.events.appendleft({"kind": "mission", "message": f"✓ WAYPOINT REACHED: {reached}"})
                    self.mission_route = self.mission_route[1:]
                if not self.waypoints:
                    self.mission_status = "COMPLETED"
                    self.events.appendleft({"kind": "mission", "message": "✓ MISSION COMPLETED"})
                    self.following_path = False
                    self.running = False
                    self.flight_state = "READY"
                    self._finalize_flight_locked("COMPLETED")
                return
            else:
                fraction = step_distance_m / max(distance_m, 1e-6)
                self.position["lat"] += delta_lat * fraction
                self.position["lng"] += delta_lng * fraction
                return
        distance_m = speed * self.simulator.dt * UAV_ROUTE_TIME_SCALE
        self.position["lat"] += distance_m * math.cos(math.radians(self.heading)) / 111111.0
        self.position["lng"] += distance_m * math.sin(math.radians(self.heading)) / (111111.0 * math.cos(math.radians(self.position["lat"])))

    @staticmethod
    def _number(value, minimum, maximum):
        value = float(value)
        if not math.isfinite(value): raise ValueError("Control value must be finite")
        return max(minimum, min(maximum, value))

    def _inject_fault(self, name, severity):
        if name not in ["cooling_degradation", "oil_pressure_degradation", "excessive_vibration", "combustion_instability", "misfire", "sensor_drift", "injector_abnormality"]: 
            raise ValueError("Unsupported fault")
        self.active_fault_name = name
        severity = max(0.0, min(1.0, severity))
        if name == "cooling_degradation": self.simulator.activate_cooling_fault(severity)
        elif name == "misfire": self.simulator.activate_misfire(severity)
        elif name == "combustion_instability": self.simulator.activate_combustion_instability(severity)
        elif name == "excessive_vibration": self.simulator.activate_vibration_fault(severity)
        elif name == "oil_pressure_degradation": self.simulator.activate_lubrication_fault(severity)
        elif name == "injector_abnormality": self.simulator.activate_injector_fault(severity)
        elif name == "sensor_drift": self.simulator.activate_sensor_drift(drift_value=35.0, severity=severity)
        # Invalidate the intelligence cache so the next tick re-evaluates with the
        # fault now active, rather than serving the pre-fault cached NORMAL result.
        self.intelligence.invalidate_cache()

    def history_data(self):
        with self.lock: return list(self.history)

    def report(self):
        with self.lock:
            if not self.history: return {"mission": "No mission", "samples": 0}
            rows = list(self.history)
            return {"mission": MISSION_NAMES.get(self.mission_name, self.mission_name), "duration_s": rows[-1]["time_s"] - rows[0]["time_s"], "samples": len(rows), "max_rpm": max(row["rpm"] for row in rows), "max_cht_c": max(row["cht_c"] for row in rows), "average_load_pct": sum(row["load_pct"] for row in rows) / len(rows), "faults": sorted({row["fault"] for row in rows if row["fault"] != "NORMAL"}), "condition": rows[-1]["status"]}


controller = TwinController()


class Client:
    def __init__(self, handler): self.handler = handler
    def send(self, state):
        data = ("data: " + json.dumps(state) + "\n\n").encode()
        try:
            self.handler.wfile.write(data); self.handler.wfile.flush()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            raise ConnectionError("SSE client disconnected")


class Handler(BaseHTTPRequestHandler):
    def _json(self, data, status=200):
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        try:
            self.end_headers()
            self.wfile.write(raw)
        except Exception:
            pass
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/state": return self._json(controller.last_state)
        if path == "/api/twin/state": return self._json(controller.last_state)
        if path == "/api/telemetry": return self._json(controller.last_state.get("telemetry", {}) if controller.last_state else {})
        if path == "/api/health": return self._json(controller.last_state.get("intelligence", {}).get("health", {}) if controller.last_state else {})
        if path == "/api/alerts": return self._json(controller.last_state.get("alerts", []) if controller.last_state else [])
        if path == "/api/diagnostics": return self._json(controller.last_state.get("intelligence", {}).get("diagnosis", {}) if controller.last_state else {})
        if path == "/api/history": return self._json(controller.history_data())
        if path == "/api/report": return self._json(controller.report())
        if path == "/api/events": return self._json(list(controller.events))
        if path == "/api/flights":
            try:
                flights = controller.influx_writer.get_flights(limit=50)
                flights.sort(key=lambda flight: float(flight.get("start_time") or 0.0), reverse=True)
                return self._json({"flights": flights})
            except Exception as exc:
                self._json({"flights": [], "error": f"Flight database temporarily unavailable: {exc}"}, 503)
                return
        if path.startswith("/api/flights/"):
            flight_id = path.split("/api/flights/", 1)[1].strip()
            if not flight_id:
                return self._json({"error": "Missing flight_id"}, 400)
            try:
                flight = controller.influx_writer.get_flight_by_id(flight_id)
                telemetry = controller.influx_writer.get_flight_telemetry(flight_id, limit=1200)
                summary = controller.influx_writer.get_flight_by_id(flight_id) or {}
                if flight is None and not telemetry:
                    return self._json({"error": "Flight not found"}, 404)
                payload = {
                    "flight": {
                        "flight_id": flight_id,
                        "mission_name": summary.get("mission_name", "UNKNOWN"),
                        "mission_key": summary.get("mission_key", "unknown"),
                        "status": summary.get("status", "COMPLETED"),
                        "start_time": summary.get("start_time"),
                        "end_time": summary.get("end_time"),
                        "duration_seconds": summary.get("duration_seconds", 0),
                    },
                    "summary": {
                        "max_altitude_m": summary.get("max_altitude_m", 0),
                        "max_rpm": summary.get("max_rpm", 0),
                        "max_cht_c": summary.get("max_cht_c", 0),
                        "max_egt_c": summary.get("max_egt_c", 0),
                        "max_vibration_rms": summary.get("max_vibration_rms", 0),
                        "minimum_health_score": summary.get("minimum_health_score", 100),
                        "fault_detected": summary.get("fault_detected", False),
                        "fault_type": summary.get("fault_type", "NORMAL"),
                        "fault_first_seen": summary.get("fault_first_seen", 0),
                        "fault_last_seen": summary.get("fault_last_seen", 0),
                        "fault_event_count": summary.get("fault_event_count", 0),
                        "telemetry_points": summary.get("telemetry_points", 0),
                    },
                    "telemetry": telemetry,
                    "health_trend": [],
                    "fault_events": ([{
                        "fault_type": summary.get("fault_type", "NORMAL"),
                        "first_seen": summary.get("fault_first_seen", 0),
                        "last_seen": summary.get("fault_last_seen", 0),
                        "sample_count": summary.get("fault_event_count", 0),
                    }] if summary.get("fault_detected") else []),
                }
                return self._json(payload)
            except Exception as exc:
                self._json({"error": f"Flight database temporarily unavailable: {exc}"}, 503)
                return
        if path == "/api/inference": return self._json(controller.last_state.get("intelligence", {}) if controller.last_state else {})
        if path == "/api/stream":
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache"); self.send_header("Connection", "keep-alive"); self.end_headers()
            client = Client(self); controller.clients.append(client); client.send(controller.last_state)
            try:
                while True: time.sleep(10); self.wfile.write(b": keepalive\n\n"); self.wfile.flush()
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                if client in controller.clients: controller.clients.remove(client)
            return
        if path == "/gcs":
            raw = (WEB_ROOT / "gcs.html").read_bytes(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(raw))); self.end_headers();
            try:
                self.wfile.write(raw)
            except Exception:
                pass
            return
        if path in {"/", "/engine", "/dashboard"}:
            raw = (WEB_ROOT / "index.html").read_bytes(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(raw))); self.end_headers();
            try:
                self.wfile.write(raw)
            except Exception:
                pass
            return
        # Static file serving for web assets
        MIME_TYPES = {".css": "text/css", ".js": "application/javascript", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".ico": "image/x-icon", ".webp": "image/webp", ".woff2": "font/woff2", ".woff": "font/woff"}
        safe_path = path.lstrip("/")
        file_path = WEB_ROOT / safe_path
        if file_path.is_file() and WEB_ROOT in file_path.resolve().parents:
            ext = file_path.suffix.lower()
            content_type = MIME_TYPES.get(ext, "application/octet-stream")
            raw = file_path.read_bytes(); self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(raw))); self.send_header("Cache-Control", "public, max-age=3600"); self.end_headers();
            try:
                self.wfile.write(raw)
            except Exception:
                pass
            return
        self.send_error(404)
    def do_POST(self):
        if self.path in {"/api/command", "/api/simulation/start", "/api/simulation/stop", "/api/simulation/reset", "/api/fault/inject", "/api/inference"}:
            try:
                if self.path == "/api/simulation/start": body = {"command": "start_uav"}
                elif self.path == "/api/simulation/stop": body = {"command": "stop_uav"}
                elif self.path == "/api/simulation/reset": body = {"command": "reset_simulation"}
                else: body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                
                if self.path == "/api/inference":
                    self._json({"ok": True, "result": controller.intelligence.process(controller.simulator.last_true_state, controller.simulator.last_sensor_state, timestamp=controller.simulator.time_s)})
                else:
                    if self.path == "/api/fault/inject": body = {"command": "inject_fault", "parameters": body}
                    controller.command(body); self._json({"ok": True, "state": controller.last_state})
            except (ValueError, TypeError, json.JSONDecodeError) as exc: self._json({"ok": False, "error": str(exc)}, 400)
        else:
            return self._json({"error": "Not found"}, 404)
    def log_message(self, *_): pass


def run():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    threading.Thread(target=lambda: [controller.tick() or time.sleep(TICK_SECONDS) for _ in iter(int, 1)], daemon=True).start()
    print(f"AERIS-TWIN Dashboard:  http://localhost:{PORT}/")
    print(f"Ground Control System: http://localhost:{PORT}/gcs")
    server.serve_forever()


if __name__ == "__main__": run()
