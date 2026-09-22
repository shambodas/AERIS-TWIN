"""
AERIS-TWIN
MQTT Telemetry Interface

Purpose
-------
Publish AERIS-TWIN engine telemetry to a ground-side
MQTT broker.

Architecture
------------

    Engine Simulator
          |
          v
     Sensor Model
          |
          v
     MQTT Publisher
          |
          v
      MQTT Broker
          |
     +----+----+
     |         |
     v         v
  Backend   Dashboard
     |
     v
  InfluxDB
     |
     v
     ML / Analytics


Design principles
-----------------

1. Structured MQTT topics
2. JSON payloads
3. QoS configuration
4. Retained system status
5. Connection handling
6. Simulation mode
7. No hard-coded credentials
8. Separation of telemetry and fault events

IMPORTANT
---------
This module does not claim that MQTT is the actual avionics
transport.

For an actual UAV:

    CAN / avionics bus
            |
            v
       Edge gateway
            |
            v
          MQTT
            |
            v
      Ground infrastructure

MQTT is therefore treated as the network/ground telemetry
layer, not as a replacement for the aircraft's internal
real-time control bus.
"""


from dataclasses import asdict, is_dataclass
import json
import logging
import time
from typing import Any


# ============================================================
# OPTIONAL PAHO IMPORT
# ============================================================

try:

    import paho.mqtt.client as mqtt

    PAHO_AVAILABLE = True

except ImportError:

    mqtt = None

    PAHO_AVAILABLE = False


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger(
    "aeris_twin.mqtt"
)


# ============================================================
# CONFIGURATION
# ============================================================

class MQTTConfig:
    """
    MQTT connection and topic configuration.
    """

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,

        username: str | None = None,
        password: str | None = None,

        client_id: str = "aeris-twin-edge",

        topic_prefix: str = "aeris-twin",

        qos: int = 1,

        keepalive: int = 60,

        retain_telemetry: bool = False,

        reconnect_delay_s: float = 5.0,
    ):

        if not broker_host:

            raise ValueError(
                "broker_host cannot be empty."
            )

        if not (
            1
            <= broker_port
            <= 65535
        ):

            raise ValueError(
                "broker_port must be between "
                "1 and 65535."
            )

        if qos not in {
            0,
            1,
            2,
        }:

            raise ValueError(
                "MQTT QoS must be 0, 1, or 2."
            )

        if keepalive <= 0:

            raise ValueError(
                "keepalive must be positive."
            )

        if reconnect_delay_s <= 0:

            raise ValueError(
                "reconnect_delay_s must be positive."
            )

        self.broker_host = (
            broker_host
        )

        self.broker_port = (
            broker_port
        )

        self.username = (
            username
        )

        self.password = (
            password
        )

        self.client_id = (
            client_id
        )

        self.topic_prefix = (
            topic_prefix.strip("/")
        )

        self.qos = qos

        self.keepalive = (
            keepalive
        )

        self.retain_telemetry = (
            retain_telemetry
        )

        self.reconnect_delay_s = (
            reconnect_delay_s
        )


# ============================================================
# TOPIC MANAGER
# ============================================================

class MQTTTopics:
    """
    Centralized AERIS-TWIN MQTT topic definitions.

    Example:

        aeris-twin/engine/telemetry

        aeris-twin/engine/fault

        aeris-twin/mission/status

        aeris-twin/system/status
    """

    def __init__(
        self,
        prefix: str = "aeris-twin",
    ):

        self.prefix = (
            prefix.strip("/")
        )


    @property
    def telemetry(self) -> str:

        return (
            f"{self.prefix}/"
            "engine/telemetry"
        )


    @property
    def fault(self) -> str:

        return (
            f"{self.prefix}/"
            "engine/fault"
        )


    @property
    def mission(self) -> str:

        return (
            f"{self.prefix}/"
            "mission/status"
        )


    @property
    def system(self) -> str:

        return (
            f"{self.prefix}/"
            "system/status"
        )


    @property
    def health(self) -> str:

        return (
            f"{self.prefix}/"
            "system/health"
        )


# ============================================================
# PAYLOAD SERIALIZER
# ============================================================

class MQTTPayloadSerializer:
    """
    Convert AERIS-TWIN states into JSON-safe dictionaries.
    """

    @staticmethod
    def convert(
        value: Any,
    ) -> Any:
        """
        Recursively convert Python objects into JSON-safe data.
        """

        if is_dataclass(value):

            return (
                MQTTPayloadSerializer
                .convert(
                    asdict(value)
                )
            )

        if isinstance(
            value,
            dict
        ):

            return {

                str(key):
                    MQTTPayloadSerializer
                    .convert(
                        item
                    )

                for key, item
                in value.items()
            }

        if isinstance(
            value,
            (
                list,
                tuple,
            )
        ):

            return [

                MQTTPayloadSerializer
                .convert(
                    item
                )

                for item in value
            ]

        if hasattr(
            value,
            "value"
        ):

            return value.value

        # Handle NumPy-like scalar values without importing
        # NumPy as a mandatory dependency.

        if hasattr(
            value,
            "item"
        ):

            try:

                return value.item()

            except Exception:

                pass

        return value


    @classmethod
    def to_json(
        cls,
        value: Any,
    ) -> str:
        """
        Serialize object to compact JSON.
        """

        converted = (
            cls.convert(
                value
            )
        )

        return json.dumps(
            converted,
            separators=(
                ",",
                ":"
            ),
        )


# ============================================================
# MQTT PUBLISHER
# ============================================================

class MQTTPublisher:
    """
    MQTT publisher for AERIS-TWIN.

    The class supports two modes:

        simulation_mode=True
            No broker required.

        simulation_mode=False
            Uses paho-mqtt.
    """

    def __init__(
        self,
        config: MQTTConfig | None = None,
        simulation_mode: bool = True,
    ):

        self.config = (
            config
            if config is not None
            else MQTTConfig()
        )

        self.topics = (
            MQTTTopics(
                self.config.topic_prefix
            )
        )

        self.simulation_mode = (
            simulation_mode
        )

        self.connected = False

        self.client = None

        self.published_messages = []

        # ----------------------------------------------------
        # Real MQTT client
        # ----------------------------------------------------

        if (
            not simulation_mode
            and not PAHO_AVAILABLE
        ):

            raise RuntimeError(

                "paho-mqtt is not installed. "

                "Install it with: "

                "pip install paho-mqtt"
            )

        if not simulation_mode:

            self._create_client()


    # ========================================================
    # CREATE CLIENT
    # ========================================================

    def _create_client(self):

        self.client = (
            mqtt.Client(
                client_id=(
                    self.config.client_id
                ),
                protocol=(
                    mqtt.MQTTv5
                ),
            )
        )

        # ----------------------------------------------------
        # Credentials
        # ----------------------------------------------------

        if (
            self.config.username
            is not None
        ):

            self.client.username_pw_set(

                self.config.username,

                self.config.password,
            )

        # ----------------------------------------------------
        # Callbacks
        # ----------------------------------------------------

        self.client.on_connect = (
            self._on_connect
        )

        self.client.on_disconnect = (
            self._on_disconnect
        )

        self.client.on_publish = (
            self._on_publish
        )


    # ========================================================
    # CALLBACK
    # ========================================================

    def _on_connect(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties=None,
    ):

        if reason_code == 0:

            self.connected = True

            logger.info(
                "Connected to MQTT broker."
            )

        else:

            self.connected = False

            logger.error(
                "MQTT connection failed: %s",
                reason_code,
            )


    # ========================================================
    # DISCONNECT CALLBACK
    # ========================================================

    def _on_disconnect(
        self,
        client,
        userdata,
        disconnect_flags,
        reason_code,
        properties=None,
    ):

        self.connected = False

        logger.warning(
            "Disconnected from MQTT broker: %s",
            reason_code,
        )


    # ========================================================
    # PUBLISH CALLBACK
    # ========================================================

    def _on_publish(
        self,
        client,
        userdata,
        mid,
        reason_code=None,
        properties=None,
    ):

        logger.debug(
            "MQTT message published: %s",
            mid,
        )


    # ========================================================
    # CONNECT
    # ========================================================

    def connect(self):

        if self.simulation_mode:

            self.connected = True

            logger.info(
                "MQTT running in simulation mode."
            )

            return True

        if self.client is None:

            self._create_client()

        try:

            self.client.connect(

                self.config.broker_host,

                self.config.broker_port,

                self.config.keepalive,
            )

            self.client.loop_start()

            # Allow callback to update connection state.

            timeout = time.time() + 5.0

            while (
                not self.connected
                and time.time() < timeout
            ):

                time.sleep(
                    0.05
                )

            return self.connected

        except Exception as exc:

            logger.exception(
                "MQTT connection error."
            )

            self.connected = False

            return False


    # ========================================================
    # DISCONNECT
    # ========================================================

    def disconnect(self):

        if self.simulation_mode:

            self.connected = False

            return

        if self.client is not None:

            try:

                self.client.loop_stop()

                self.client.disconnect()

            except Exception:

                logger.exception(
                    "MQTT disconnect error."
                )

        self.connected = False


    # ========================================================
    # PUBLISH RAW
    # ========================================================

    def publish(
        self,
        topic: str,
        payload: Any,
        qos: int | None = None,
        retain: bool | None = None,
    ) -> bool:
        """
        Publish one JSON MQTT message.
        """

        if not topic:

            raise ValueError(
                "MQTT topic cannot be empty."
            )

        if qos is None:

            qos = self.config.qos

        if retain is None:

            retain = (
                self.config
                .retain_telemetry
            )

        if qos not in {
            0,
            1,
            2,
        }:

            raise ValueError(
                "MQTT QoS must be 0, 1, or 2."
            )

        message = (
            MQTTPayloadSerializer
            .to_json(
                payload
            )
        )

        # ----------------------------------------------------
        # Simulation mode
        # ----------------------------------------------------

        if self.simulation_mode:

            self.published_messages.append({

                "topic":
                    topic,

                "payload":
                    message,

                "qos":
                    qos,

                "retain":
                    retain,

                "timestamp":
                    time.time(),
            })

            return True

        # ----------------------------------------------------
        # Real MQTT
        # ----------------------------------------------------

        if not self.connected:

            logger.warning(
                "MQTT publish attempted "
                "while disconnected."
            )

            return False

        try:

            result = (
                self.client.publish(

                    topic,

                    message,

                    qos=qos,

                    retain=retain,
                )
            )

            if result.rc != (
                mqtt.MQTT_ERR_SUCCESS
            ):

                logger.error(
                    "MQTT publish failed: %s",
                    result.rc,
                )

                return False

            return True

        except Exception:

            logger.exception(
                "MQTT publish exception."
            )

            return False


    # ========================================================
    # ENGINE TELEMETRY
    # ========================================================

    def publish_engine_telemetry(
        self,
        sensor_state,
        mission_phase: str = "UNKNOWN",
        simulation_time_s: float = 0.0,
    ) -> bool:
        """
        Publish measured engine telemetry.

        The payload contains sensor observations rather than
        Digital Twin ground-truth values.
        """

        payload = {

            "timestamp_utc":
                time.time(),

            "simulation_time_s":
                simulation_time_s,

            "mission_phase":
                mission_phase,

            "telemetry":
                MQTTPayloadSerializer
                .convert(
                    sensor_state
                ),
        }

        return self.publish(

            topic=self.topics.telemetry,

            payload=payload,
        )


    # ========================================================
    # FAULT EVENT
    # ========================================================

    def publish_fault(
        self,
        fault_type: str,
        severity: float,
        fault_label: int,
        simulation_time_s: float = 0.0,
        mission_phase: str = "UNKNOWN",
    ) -> bool:
        """
        Publish fault information as a separate event.

        Keeping faults separate from high-rate telemetry makes
        downstream event processing easier.
        """

        payload = {

            "timestamp_utc":
                time.time(),

            "simulation_time_s":
                simulation_time_s,

            "mission_phase":
                mission_phase,

            "fault_type":
                fault_type,

            "fault_severity":
                severity,

            "fault_label":
                fault_label,
        }

        return self.publish(

            topic=self.topics.fault,

            payload=payload,

            qos=1,

            retain=False,
        )


    # ========================================================
    # MISSION STATUS
    # ========================================================

    def publish_mission_status(
        self,
        mission_state,
    ) -> bool:
        """
        Publish mission state.
        """

        payload = {

            "timestamp_utc":
                time.time(),

            "mission":
                MQTTPayloadSerializer
                .convert(
                    mission_state
                ),
        }

        return self.publish(

            topic=self.topics.mission,

            payload=payload,

            qos=1,
        )


    # ========================================================
    # SYSTEM STATUS
    # ========================================================

    def publish_system_status(
        self,
        status: str,
        details: dict | None = None,
    ) -> bool:
        """
        Publish system status.
        """

        payload = {

            "timestamp_utc":
                time.time(),

            "status":
                status,

            "details":
                details
                if details is not None
                else {},
        }

        return self.publish(

            topic=self.topics.system,

            payload=payload,

            qos=1,

            retain=True,
        )


    # ========================================================
    # HEALTH
    # ========================================================

    def publish_health(
        self,
        simulator_time_s: float,
        telemetry_rate_hz: float,
        active_fault: str,
    ) -> bool:
        """
        Publish edge-system health information.
        """

        payload = {

            "timestamp_utc":
                time.time(),

            "simulator_time_s":
                simulator_time_s,

            "telemetry_rate_hz":
                telemetry_rate_hz,

            "active_fault":
                active_fault,

            "mqtt_connected":
                self.connected,
        }

        return self.publish(

            topic=self.topics.health,

            payload=payload,

            qos=1,

            retain=True,
        )


    # ========================================================
    # GET SIMULATION MESSAGES
    # ========================================================

    def get_simulated_messages(
        self,
    ) -> list[dict]:
        """
        Return messages generated in simulation mode.
        """

        return list(
            self.published_messages
        )


    # ========================================================
    # CLEAR SIMULATED MESSAGES
    # ========================================================

    def clear_simulated_messages(
        self,
    ):

        self.published_messages.clear()


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print(
        "\n"
        + "=" * 90
    )

    print(
        "AERIS-TWIN MQTT TELEMETRY TEST"
    )

    print(
        "=" * 90
    )

    # --------------------------------------------------------
    # Create simulation MQTT publisher
    # --------------------------------------------------------

    config = MQTTConfig(

        broker_host="localhost",

        broker_port=1883,

        client_id="aeris-twin-demo",

        topic_prefix="aeris-twin",

        qos=1,
    )

    publisher = MQTTPublisher(

        config=config,

        simulation_mode=True,
    )

    # --------------------------------------------------------
    # Connect
    # --------------------------------------------------------

    publisher.connect()

    print(
        "\nMQTT simulation mode:"
    )

    print(
        publisher.connected
    )

    # --------------------------------------------------------
    # Synthetic sensor telemetry
    # --------------------------------------------------------

    sensor_state = {

        "rpm":
            3500.0,

        "manifold_pressure_kpa":
            88.2,

        "intake_temperature_c":
            34.5,

        "fuel_flow_kg_s":
            0.0024,

        "torque_nm":
            105.0,

        "power_kw":
            38.5,

        "cht_cylinder_1_c":
            165.2,

        "cht_cylinder_2_c":
            168.4,

        "cht_cylinder_3_c":
            167.1,

        "cht_cylinder_4_c":
            166.7,

        "oil_temperature_c":
            94.3,

        "oil_pressure_psi":
            57.2,

        "oil_flow_l_min":
            5.2,

        "battery_voltage_v":
            24.1,

        "battery_current_a":
            2.4,

        "battery_soc":
            0.91,

        "vibration_rms":
            0.32,

        "vibration_peak":
            0.91,

        "vibration_0_5x":
            0.05,

        "vibration_1x":
            0.23,

        "vibration_2x":
            0.07,
    }

    # --------------------------------------------------------
    # Telemetry
    # --------------------------------------------------------

    telemetry_ok = (
        publisher
        .publish_engine_telemetry(

            sensor_state=sensor_state,

            mission_phase="CRUISE",

            simulation_time_s=420.0,
        )
    )

    print(
        "\nTelemetry published:"
    )

    print(
        telemetry_ok
    )

    # --------------------------------------------------------
    # Fault
    # --------------------------------------------------------

    fault_ok = (
        publisher.publish_fault(

            fault_type="MISFIRE",

            severity=0.85,

            fault_label=1,

            simulation_time_s=425.0,

            mission_phase="CRUISE",
        )
    )

    print(
        "\nFault published:"
    )

    print(
        fault_ok
    )

    # --------------------------------------------------------
    # Mission
    # --------------------------------------------------------

    mission_ok = (
        publisher
        .publish_mission_status({

            "phase":
                "CRUISE",

            "altitude_m":
                5000.0,

            "airspeed_mps":
                44.0,

            "throttle_pct":
                67.0,

            "mission_progress":
                0.42,
        })
    )

    print(
        "\nMission status published:"
    )

    print(
        mission_ok
    )

    # --------------------------------------------------------
    # Health
    # --------------------------------------------------------

    publisher.publish_health(

        simulator_time_s=425.0,

        telemetry_rate_hz=10.0,

        active_fault="MISFIRE",
    )

    # --------------------------------------------------------
    # Show generated messages
    # --------------------------------------------------------

    print(
        "\nGENERATED MQTT MESSAGES"
    )

    print(
        "-" * 90
    )

    for message in (
        publisher
        .get_simulated_messages()
    ):

        print(
            f"\nTOPIC: "
            f"{message['topic']}"
        )

        print(
            f"QoS: "
            f"{message['qos']}"
        )

        print(
            f"PAYLOAD:"
        )

        print(
            message["payload"]
        )

    publisher.disconnect()

    print(
        "\n"
        + "=" * 90
    )

    print(
        "MQTT TELEMETRY TEST COMPLETE"
    )

    print(
        "=" * 90
    )