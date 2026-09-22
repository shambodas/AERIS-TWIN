"""
AERIS-TWIN
CAN Telemetry Interface

Purpose
-------
Convert measured engine telemetry into deterministic CAN-style
frames and decode those frames back into engineering values.

This module is a simulation/prototype CAN layer.

It does NOT require physical CAN hardware.

Architecture
------------

    Sensor Model
         |
         v
    SensorState
         |
         v
    CAN Encoder
         |
         v
    CAN Frames
         |
         +------> CAN hardware / SocketCAN later
         |
         v
    CAN Decoder
         |
         v
    Telemetry Dictionary


Design principles
-----------------

1. Fixed CAN message identifiers
2. Fixed payload layout
3. Explicit scaling factors
4. Explicit engineering units
5. Range validation
6. CRC/checksum for application-level integrity
7. Deterministic encoding/decoding

IMPORTANT
---------
The message IDs and packing used here are AERIS-TWIN
prototype definitions. They are NOT claimed to be an official
aircraft CAN protocol.

When integrating with a real engine/UAV, the DBC/message
definition must be replaced by the aircraft's actual bus
specification.
"""


from dataclasses import dataclass
from enum import IntEnum
import struct
import time


# ============================================================
# CAN FRAME
# ============================================================

@dataclass
class CANFrame:
    """
    Generic CAN frame.

    arbitration_id:
        Standard 11-bit CAN identifier.

    data:
        CAN payload. Classic CAN allows up to 8 bytes.

    timestamp:
        Host/simulation timestamp.

    dlc:
        Data length code.
    """

    arbitration_id: int

    data: bytes

    timestamp: float

    dlc: int


# ============================================================
# MESSAGE IDENTIFIERS
# ============================================================

class CANMessageID(IntEnum):
    """
    AERIS-TWIN prototype CAN message identifiers.

    These are internal project IDs.

    They should be replaced by the target UAV/engine CAN
    specification during real hardware integration.
    """

    ENGINE_CORE = 0x100

    ENGINE_THERMAL = 0x101

    ENGINE_OIL = 0x102

    ENGINE_ELECTRICAL = 0x103

    ENGINE_VIBRATION = 0x104

    MISSION_STATUS = 0x105

    FAULT_STATUS = 0x106


# ============================================================
# CAN CONSTANTS
# ============================================================

MAX_STANDARD_CAN_ID = 0x7FF

MAX_CAN_DLC = 8


# ============================================================
# ENCODER
# ============================================================

class CANTelemetryEncoder:
    """
    Encode AERIS-TWIN sensor measurements into CAN frames.

    Scaling convention
    ------------------

    Integer representation is used to avoid transmitting
    floating-point values directly.

    Example:

        RPM = 3500.4

        scale = 0.1 RPM/count

        transmitted integer ≈ 35004
    """

    # --------------------------------------------------------
    # Scaling
    # --------------------------------------------------------

    RPM_SCALE = 0.1

    PRESSURE_SCALE = 0.01

    TEMPERATURE_SCALE = 0.1

    FUEL_FLOW_SCALE = 1_000_000.0

    TORQUE_SCALE = 0.1

    POWER_SCALE = 0.01

    OIL_FLOW_SCALE = 0.01

    VOLTAGE_SCALE = 0.01

    CURRENT_SCALE = 0.01

    SOC_SCALE = 1000.0

    VIBRATION_SCALE = 1000.0


    # ========================================================
    # VALIDATION
    # ========================================================

    @staticmethod
    def _validate_can_id(
        arbitration_id: int,
    ):

        if not (
            0
            <= arbitration_id
            <= MAX_STANDARD_CAN_ID
        ):

            raise ValueError(
                "CAN ID must be a valid "
                "11-bit standard identifier."
            )


    @staticmethod
    def _clip_uint16(
        value: int,
    ) -> int:

        return max(
            0,
            min(
                65535,
                int(value)
            )
        )


    @staticmethod
    def _clip_int16(
        value: int,
    ) -> int:

        return max(
            -32768,
            min(
                32767,
                int(value)
            )
        )


    # ========================================================
    # UINT16
    # ========================================================

    @staticmethod
    def _encode_uint16(
        value: float,
        scale: float,
    ) -> bytes:

        if scale <= 0:

            raise ValueError(
                "Scale must be positive."
            )

        raw = round(
            value * scale
        )

        raw = max(
            0,
            min(
                65535,
                raw
            )
        )

        return struct.pack(
            "<H",
            raw
        )


    # ========================================================
    # INT16
    # ========================================================

    @staticmethod
    def _encode_int16(
        value: float,
        scale: float,
    ) -> bytes:

        if scale <= 0:

            raise ValueError(
                "Scale must be positive."
            )

        raw = round(
            value * scale
        )

        raw = max(
            -32768,
            min(
                32767,
                raw
            )
        )

        return struct.pack(
            "<h",
            raw
        )


    # ========================================================
    # CRC
    # ========================================================

    @staticmethod
    def calculate_checksum(
        data: bytes,
    ) -> int:
        """
        Simple 8-bit additive checksum.

        This is an application-level integrity check.

        It is NOT a replacement for the CAN protocol's own
        physical-layer CRC.
        """

        return sum(data) & 0xFF


    # ========================================================
    # FRAME BUILDER
    # ========================================================

    @classmethod
    def _frame(
        cls,
        message_id: CANMessageID,
        payload_without_checksum: bytes,
        timestamp: float | None = None,
    ) -> CANFrame:
        """
        Construct an 8-byte CAN frame.

        Last byte is the application checksum.
        """

        cls._validate_can_id(
            int(message_id)
        )

        if len(
            payload_without_checksum
        ) > 7:

            raise ValueError(
                "Payload must be <= 7 bytes "
                "when checksum is enabled."
            )

        data = (
            payload_without_checksum
            + bytes(
                [cls.calculate_checksum(
                    payload_without_checksum
                )]
            )
        )

        data = data.ljust(
            8,
            b"\x00"
        )

        return CANFrame(

            arbitration_id=int(
                message_id
            ),

            data=data,

            timestamp=(
                time.time()
                if timestamp is None
                else timestamp
            ),

            dlc=8,
        )


    # ========================================================
    # ENGINE CORE
    # ========================================================

    @classmethod
    def encode_engine_core(
        cls,
        sensor_state,
        timestamp: float | None = None,
    ) -> CANFrame:
        """
        ENGINE_CORE message.

        Byte layout
        -----------

        Bytes 0-1:
            RPM

        Bytes 2-3:
            Manifold pressure

        Bytes 4-5:
            Torque

        Bytes 6:
            Throttle percentage

        Byte 7:
            Checksum

        Units
        -----

        RPM:
            0.1 RPM/count

        Pressure:
            0.01 kPa/count

        Torque:
            0.1 Nm/count

        Throttle:
            1 %/count
        """

        rpm = cls._encode_uint16(
            sensor_state.rpm,
            cls.RPM_SCALE
        )

        manifold_pressure = (
            cls._encode_uint16(
                sensor_state
                .manifold_pressure_kpa,
                cls.PRESSURE_SCALE
            )
        )

        torque = cls._encode_uint16(
            sensor_state.torque_nm,
            cls.TORQUE_SCALE
        )

        # Engine core has room for only 7 bytes before checksum.
        # RPM + pressure + torque = 6 bytes.
        # We therefore encode throttle separately in byte 6.

        throttle = max(
            0,
            min(
                100,
                round(
                    sensor_state
                    .get(
                        "throttle_pct",
                        0
                    )
                )
                if isinstance(
                    sensor_state,
                    dict
                )
                else 0
            )
        )

        payload = (
            rpm
            + manifold_pressure
            + torque
            + bytes([throttle])
        )

        return cls._frame(

            CANMessageID.ENGINE_CORE,

            payload,

            timestamp,
        )


    # ========================================================
    # THERMAL
    # ========================================================

    @classmethod
    def encode_thermal(
        cls,
        sensor_state,
        timestamp: float | None = None,
    ) -> CANFrame:
        """
        ENGINE_THERMAL message.

        Bytes 0-1:
            CHT cylinder 1

        Bytes 2-3:
            CHT cylinder 2

        Bytes 4-5:
            CHT cylinder 3

        Byte 6:
            CHT cylinder 4 compressed integer

        Byte 7:
            Checksum

        To preserve full resolution for all four cylinders,
        a second thermal message would normally be preferable.
        For the SIH prototype we instead use 0.5°C resolution
        for byte 6/remaining compressed representation.

        Here we use the four-cylinder values as uint16 pairs
        for CHT1-3 and a compact 8-bit representation for CHT4.
        """

        cht1 = cls._encode_uint16(
            sensor_state.cht_cylinder_1_c,
            cls.TEMPERATURE_SCALE
        )

        cht2 = cls._encode_uint16(
            sensor_state.cht_cylinder_2_c,
            cls.TEMPERATURE_SCALE
        )

        cht3 = cls._encode_uint16(
            sensor_state.cht_cylinder_3_c,
            cls.TEMPERATURE_SCALE
        )

        # CHT4 is compressed to integer degrees.
        cht4 = max(
            0,
            min(
                255,
                round(
                    sensor_state
                    .cht_cylinder_4_c
                )
            )
        )

        # 2 + 2 + 2 + 1 = 7 bytes.
        payload = (
            cht1
            + cht2
            + cht3
            + bytes([cht4])
        )

        return cls._frame(

            CANMessageID.ENGINE_THERMAL,

            payload,

            timestamp,
        )


    # ========================================================
    # OIL
    # ========================================================

    @classmethod
    def encode_oil(
        cls,
        sensor_state,
        timestamp: float | None = None,
    ) -> CANFrame:
        """
        ENGINE_OIL message.

        Bytes 0-1:
            Oil temperature

        Bytes 2-3:
            Oil pressure

        Bytes 4-5:
            Oil flow

        Byte 6:
            Reserved

        Byte 7:
            Checksum
        """

        oil_temperature = (
            cls._encode_uint16(
                sensor_state
                .oil_temperature_c,
                cls.TEMPERATURE_SCALE
            )
        )

        oil_pressure = (
            cls._encode_uint16(
                sensor_state
                .oil_pressure_psi,
                cls.PRESSURE_SCALE
            )
        )

        oil_flow = (
            cls._encode_uint16(
                sensor_state
                .oil_flow_l_min,
                cls.OIL_FLOW_SCALE
            )
        )

        payload = (
            oil_temperature
            + oil_pressure
            + oil_flow
            + bytes([0])
        )

        return cls._frame(

            CANMessageID.ENGINE_OIL,

            payload,

            timestamp,
        )


    # ========================================================
    # ELECTRICAL
    # ========================================================

    @classmethod
    def encode_electrical(
        cls,
        sensor_state,
        timestamp: float | None = None,
    ) -> CANFrame:
        """
        ENGINE_ELECTRICAL message.

        Bytes 0-1:
            Battery voltage

        Bytes 2-3:
            Battery current

        Bytes 4-5:
            Battery SOC

        Byte 6:
            Reserved

        Byte 7:
            Checksum
        """

        voltage = (
            cls._encode_uint16(
                sensor_state
                .battery_voltage_v,
                cls.VOLTAGE_SCALE
            )
        )

        current = (
            cls._encode_int16(
                sensor_state
                .battery_current_a,
                cls.CURRENT_SCALE
            )
        )

        soc = (
            cls._encode_uint16(
                sensor_state
                .battery_soc,
                cls.SOC_SCALE
            )
        )

        payload = (
            voltage
            + current
            + soc
            + bytes([0])
        )

        return cls._frame(

            CANMessageID.ENGINE_ELECTRICAL,

            payload,

            timestamp,
        )


    # ========================================================
    # VIBRATION
    # ========================================================

    @classmethod
    def encode_vibration(
        cls,
        sensor_state,
        timestamp: float | None = None,
    ) -> CANFrame:
        """
        ENGINE_VIBRATION message.

        Bytes 0-1:
            RMS

        Bytes 2-3:
            Peak

        Byte 4:
            0.5X order

        Byte 5:
            1X order

        Byte 6:
            2X order

        Byte 7:
            Checksum
        """

        rms = cls._encode_uint16(
            sensor_state.vibration_rms,
            cls.VIBRATION_SCALE
        )

        peak = cls._encode_uint16(
            sensor_state.vibration_peak,
            cls.VIBRATION_SCALE
        )

        order_05x = max(
            0,
            min(
                255,
                round(
                    sensor_state
                    .vibration_0_5x
                    * 100
                )
            )
        )

        order_1x = max(
            0,
            min(
                255,
                round(
                    sensor_state
                    .vibration_1x
                    * 100
                )
            )
        )

        order_2x = max(
            0,
            min(
                255,
                round(
                    sensor_state
                    .vibration_2x
                    * 100
                )
            )
        )

        payload = (
            rms
            + peak
            + bytes([
                order_05x,
                order_1x,
                order_2x,
            ])
        )

        return cls._frame(

            CANMessageID.ENGINE_VIBRATION,

            payload,

            timestamp,
        )


    # ========================================================
    # FAULT STATUS
    # ========================================================

    @classmethod
    def encode_fault_status(
        cls,
        fault_type: str,
        severity: float,
        fault_label: int,
        timestamp: float | None = None,
    ) -> CANFrame:
        """
        FAULT_STATUS message.

        Byte 0:
            ML fault label

        Byte 1:
            Severity 0-255

        Bytes 2-6:
            Fault type ASCII code, truncated/padded

        Byte 7:
            Checksum
        """

        severity_raw = max(
            0,
            min(
                255,
                round(
                    severity
                    * 255
                )
            )
        )

        fault_bytes = (
            fault_type
            .encode(
                "ascii",
                errors="replace"
            )[:5]
            .ljust(
                5,
                b"\x00"
            )
        )

        payload = (
            bytes([
                fault_label,
                severity_raw,
            ])
            + fault_bytes
        )

        return cls._frame(

            CANMessageID.FAULT_STATUS,

            payload,

            timestamp,
        )


    # ========================================================
    # ENCODE COMPLETE SENSOR STATE
    # ========================================================

    @classmethod
    def encode_all(
        cls,
        sensor_state,
        fault_type: str = "NORMAL",
        fault_severity: float = 0.0,
        fault_label: int = 0,
        timestamp: float | None = None,
    ) -> list[CANFrame]:
        """
        Encode the complete measured sensor state into multiple
        CAN frames.
        """

        return [

            cls.encode_engine_core(
                sensor_state,
                timestamp,
            ),

            cls.encode_thermal(
                sensor_state,
                timestamp,
            ),

            cls.encode_oil(
                sensor_state,
                timestamp,
            ),

            cls.encode_electrical(
                sensor_state,
                timestamp,
            ),

            cls.encode_vibration(
                sensor_state,
                timestamp,
            ),

            cls.encode_fault_status(

                fault_type,

                fault_severity,

                fault_label,

                timestamp,
            ),
        ]


# ============================================================
# DECODER
# ============================================================

class CANTelemetryDecoder:
    """
    Decode AERIS-TWIN CAN frames back into engineering values.

    This is primarily used for:

        - testing
        - telemetry gateway development
        - replay
        - validation
    """

    # ========================================================
    # CHECKSUM
    # ========================================================

    @staticmethod
    def verify_checksum(
        frame: CANFrame,
    ) -> bool:
        """
        Verify the application-level checksum.
        """

        if len(frame.data) != 8:

            return False

        payload = (
            frame.data[:7]
        )

        expected = (
            frame.data[7]
        )

        actual = (
            CANTelemetryEncoder
            .calculate_checksum(
                payload
            )
        )

        return (
            actual
            == expected
        )


    # ========================================================
    # UINT16
    # ========================================================

    @staticmethod
    def _decode_uint16(
        data: bytes,
        offset: int,
        scale: float,
    ) -> float:

        raw = struct.unpack_from(
            "<H",
            data,
            offset
        )[0]

        return (
            raw
            / scale
        )


    # ========================================================
    # INT16
    # ========================================================

    @staticmethod
    def _decode_int16(
        data: bytes,
        offset: int,
        scale: float,
    ) -> float:

        raw = struct.unpack_from(
            "<h",
            data,
            offset
        )[0]

        return (
            raw
            / scale
        )


    # ========================================================
    # ENGINE CORE
    # ========================================================

    @classmethod
    def decode_engine_core(
        cls,
        frame: CANFrame,
    ) -> dict:
        """
        Decode ENGINE_CORE.
        """

        if (
            frame.arbitration_id
            != CANMessageID.ENGINE_CORE
        ):

            raise ValueError(
                "Incorrect CAN message ID."
            )

        if not cls.verify_checksum(
            frame
        ):

            raise ValueError(
                "CAN application checksum failed."
            )

        data = frame.data

        return {

            "rpm":
                cls._decode_uint16(
                    data,
                    0,
                    CANTelemetryEncoder
                    .RPM_SCALE
                ),

            "manifold_pressure_kpa":
                cls._decode_uint16(
                    data,
                    2,
                    CANTelemetryEncoder
                    .PRESSURE_SCALE
                ),

            "torque_nm":
                cls._decode_uint16(
                    data,
                    4,
                    CANTelemetryEncoder
                    .TORQUE_SCALE
                ),

            "throttle_pct":
                data[6],
        }


    # ========================================================
    # THERMAL
    # ========================================================

    @classmethod
    def decode_thermal(
        cls,
        frame: CANFrame,
    ) -> dict:

        if (
            frame.arbitration_id
            != CANMessageID.ENGINE_THERMAL
        ):

            raise ValueError(
                "Incorrect CAN message ID."
            )

        if not cls.verify_checksum(
            frame
        ):

            raise ValueError(
                "CAN application checksum failed."
            )

        data = frame.data

        return {

            "cht_cylinder_1_c":
                cls._decode_uint16(
                    data,
                    0,
                    CANTelemetryEncoder
                    .TEMPERATURE_SCALE
                ),

            "cht_cylinder_2_c":
                cls._decode_uint16(
                    data,
                    2,
                    CANTelemetryEncoder
                    .TEMPERATURE_SCALE
                ),

            "cht_cylinder_3_c":
                cls._decode_uint16(
                    data,
                    4,
                    CANTelemetryEncoder
                    .TEMPERATURE_SCALE
                ),

            "cht_cylinder_4_c":
                float(
                    data[6]
                ),
        }


    # ========================================================
    # OIL
    # ========================================================

    @classmethod
    def decode_oil(
        cls,
        frame: CANFrame,
    ) -> dict:

        if (
            frame.arbitration_id
            != CANMessageID.ENGINE_OIL
        ):

            raise ValueError(
                "Incorrect CAN message ID."
            )

        if not cls.verify_checksum(
            frame
        ):

            raise ValueError(
                "CAN application checksum failed."
            )

        data = frame.data

        return {

            "oil_temperature_c":
                cls._decode_uint16(
                    data,
                    0,
                    CANTelemetryEncoder
                    .TEMPERATURE_SCALE
                ),

            "oil_pressure_psi":
                cls._decode_uint16(
                    data,
                    2,
                    CANTelemetryEncoder
                    .PRESSURE_SCALE
                ),

            "oil_flow_l_min":
                cls._decode_uint16(
                    data,
                    4,
                    CANTelemetryEncoder
                    .OIL_FLOW_SCALE
                ),
        }


    # ========================================================
    # ELECTRICAL
    # ========================================================

    @classmethod
    def decode_electrical(
        cls,
        frame: CANFrame,
    ) -> dict:

        if (
            frame.arbitration_id
            != CANMessageID.ENGINE_ELECTRICAL
        ):

            raise ValueError(
                "Incorrect CAN message ID."
            )

        if not cls.verify_checksum(
            frame
        ):

            raise ValueError(
                "CAN application checksum failed."
            )

        data = frame.data

        return {

            "battery_voltage_v":
                cls._decode_uint16(
                    data,
                    0,
                    CANTelemetryEncoder
                    .VOLTAGE_SCALE
                ),

            "battery_current_a":
                cls._decode_int16(
                    data,
                    2,
                    CANTelemetryEncoder
                    .CURRENT_SCALE
                ),

            "battery_soc":
                cls._decode_uint16(
                    data,
                    4,
                    CANTelemetryEncoder
                    .SOC_SCALE
                ),
        }


    # ========================================================
    # VIBRATION
    # ========================================================

    @classmethod
    def decode_vibration(
        cls,
        frame: CANFrame,
    ) -> dict:

        if (
            frame.arbitration_id
            != CANMessageID.ENGINE_VIBRATION
        ):

            raise ValueError(
                "Incorrect CAN message ID."
            )

        if not cls.verify_checksum(
            frame
        ):

            raise ValueError(
                "CAN application checksum failed."
            )

        data = frame.data

        return {

            "vibration_rms":
                cls._decode_uint16(
                    data,
                    0,
                    CANTelemetryEncoder
                    .VIBRATION_SCALE
                ),

            "vibration_peak":
                cls._decode_uint16(
                    data,
                    2,
                    CANTelemetryEncoder
                    .VIBRATION_SCALE
                ),

            "vibration_0_5x":
                data[4] / 100.0,

            "vibration_1x":
                data[5] / 100.0,

            "vibration_2x":
                data[6] / 100.0,
        }


    # ========================================================
    # FAULT STATUS
    # ========================================================

    @classmethod
    def decode_fault_status(
        cls,
        frame: CANFrame,
    ) -> dict:

        if (
            frame.arbitration_id
            != CANMessageID.FAULT_STATUS
        ):

            raise ValueError(
                "Incorrect CAN message ID."
            )

        if not cls.verify_checksum(
            frame
        ):

            raise ValueError(
                "CAN application checksum failed."
            )

        data = frame.data

        fault_text = (
            data[2:7]
            .rstrip(
                b"\x00"
            )
            .decode(
                "ascii",
                errors="replace"
            )
        )

        return {

            "fault_label":
                data[0],

            "fault_severity":
                data[1]
                / 255.0,

            "fault_type":
                fault_text,
        }


# ============================================================
# CAN TELEMETRY BUS
# ============================================================

class SimulatedCANBus:
    """
    In-memory CAN bus for AERIS-TWIN.

    This lets us test the complete telemetry path without
    physical CAN hardware.

    Later this class can be replaced by:

        - python-can
        - SocketCAN
        - UAV CAN interface
        - hardware CAN adapter
    """

    def __init__(self):

        self.frames: list[CANFrame] = []


    # ========================================================
    # SEND
    # ========================================================

    def send(
        self,
        frame: CANFrame,
    ):

        if len(frame.data) != frame.dlc:

            raise ValueError(
                "Frame data length does not "
                "match DLC."
            )

        self.frames.append(
            frame
        )


    # ========================================================
    # RECEIVE
    # ========================================================

    def receive_all(
        self,
    ) -> list[CANFrame]:

        frames = list(
            self.frames
        )

        self.frames.clear()

        return frames


    # ========================================================
    # PENDING
    # ========================================================

    def pending_count(
        self,
    ) -> int:

        return len(
            self.frames
        )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print(
        "\n"
        + "=" * 90
    )

    print(
        "AERIS-TWIN CAN TELEMETRY TEST"
    )

    print(
        "=" * 90
    )

    # --------------------------------------------------------
    # Import sensor state
    # --------------------------------------------------------

    from sensors.sensor_model import (
        SensorModel,
    )

    # --------------------------------------------------------
    # Synthetic measured state
    # --------------------------------------------------------

    sensor_model = SensorModel(
        random_seed=42
    )

    true_state = {

        "rpm":
            3500.0,

        "manifold_pressure_kpa":
            88.0,

        "intake_temperature_c":
            32.0,

        "fuel_flow_kg_s":
            0.0024,

        "torque_nm":
            105.0,

        "power_kw":
            38.5,

        "cht_c":
            [
                165.0,
                170.0,
                168.0,
                166.0,
            ],

        "egt_c":
            [
                680.0,
                690.0,
                685.0,
                688.0,
            ],

        "oil_temperature_c":
            94.0,

        "oil_pressure_psi":
            57.0,

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

    sensor_state = (
        sensor_model.measure_engine(
            true_state
        )
    )

    # --------------------------------------------------------
    # Encode
    # --------------------------------------------------------

    frames = (
        CANTelemetryEncoder.encode_all(

            sensor_state,

            fault_type="NORMAL",

            fault_severity=0.0,

            fault_label=0,
        )
    )

    print(
        "\nGENERATED CAN FRAMES"
    )

    print(
        "-" * 90
    )

    for frame in frames:

        print(

            f"ID=0x"
            f"{frame.arbitration_id:03X} | "

            f"DLC={frame.dlc} | "

            f"DATA="
            f"{frame.data.hex(' ')}"
        )

    # --------------------------------------------------------
    # Decode
    # --------------------------------------------------------

    print(
        "\nDECODED ENGINE CORE"
    )

    print(
        "-" * 90
    )

    decoded_core = (
        CANTelemetryDecoder
        .decode_engine_core(
            frames[0]
        )
    )

    for key, value in (
        decoded_core.items()
    ):

        print(
            f"{key}: {value}"
        )

    # --------------------------------------------------------
    # Decode thermal
    # --------------------------------------------------------

    print(
        "\nDECODED THERMAL"
    )

    print(
        "-" * 90
    )

    decoded_thermal = (
        CANTelemetryDecoder
        .decode_thermal(
            frames[1]
        )
    )

    for key, value in (
        decoded_thermal.items()
    ):

        print(
            f"{key}: {value}"
        )

    # --------------------------------------------------------
    # Simulated bus
    # --------------------------------------------------------

    bus = (
        SimulatedCANBus()
    )

    for frame in frames:

        bus.send(
            frame
        )

    print(
        "\nSIMULATED CAN BUS"
    )

    print(
        "-" * 90
    )

    print(
        f"Frames waiting: "
        f"{bus.pending_count()}"
    )

    received = (
        bus.receive_all()
    )

    print(
        f"Frames received: "
        f"{len(received)}"
    )

    print(
        "\nCAN TELEMETRY TEST COMPLETE"
    )

    print(
        "=" * 90
    )