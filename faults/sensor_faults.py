"""
AERIS-TWIN
Sensor Fault Model

Purpose
-------
Generate measurement faults independently from physical
engine faults.

Supported fault:

    SENSOR_DRIFT

The engine's true physical state remains unchanged.

Only the observed sensor value is modified later by
sensors/sensor_model.py.

This separation is essential for distinguishing:

    ENGINE FAULT
        from
    SENSOR FAULT
"""


from dataclasses import dataclass


@dataclass
class SensorDriftFault:
    """
    Sensor drift state.
    """

    target_sensor: str = "CHT"

    drift_value: float = 0.0

    severity: float = 0.0

    active: bool = False


class SensorFaultModel:
    """
    Sensor-fault scenario generator.

    Drift is expressed in engineering units appropriate for
    the target sensor.

    Examples:

        CHT  -> °C
        EGT  -> °C
        Oil temperature -> °C
        RPM -> RPM
        Oil pressure -> psi
    """

    def __init__(self):

        self.fault = (
            SensorDriftFault()
        )


    # ========================================================
    # ACTIVATE DRIFT
    # ========================================================

    def activate_drift(
        self,
        target_sensor: str = "CHT",
        drift_value: float = 10.0,
        severity: float = 0.7,
    ):
        """
        Activate sensor drift.
        """

        if not target_sensor:

            raise ValueError(
                "target_sensor cannot be empty."
            )

        self.fault = (
            SensorDriftFault(

                target_sensor=(
                    target_sensor
                ),

                drift_value=(
                    float(drift_value)
                ),

                severity=max(
                    0.0,
                    min(
                        1.0,
                        float(severity)
                    )
                ),

                active=True,
            )
        )


    # ========================================================
    # CLEAR
    # ========================================================

    def clear(self):

        self.fault = (
            SensorDriftFault()
        )


    # ========================================================
    # STATUS
    # ========================================================

    def is_active(self) -> bool:

        return self.fault.active


    # ========================================================
    # APPLY DRIFT
    # ========================================================

    def apply(
        self,
        sensor_name: str,
        true_value: float,
    ) -> float:
        """
        Apply sensor drift to an observed measurement.

        The physical true_value is never modified.

        Returns:
            Sensor-observed value.
        """

        if not self.fault.active:

            return true_value

        if (
            sensor_name
            != self.fault.target_sensor
        ):

            return true_value

        # Gradual drift scaled by severity.
        drift = (
            self.fault.drift_value
            * self.fault.severity
        )

        return (
            true_value
            + drift
        )


    # ========================================================
    # GET EFFECT
    # ========================================================

    def get_effect(self) -> dict:
        """
        Return sensor fault metadata.
        """

        if not self.fault.active:

            return {

                "type": "NONE",

                "severity": 0.0,

                "target_sensor": None,

                "drift_value": 0.0,
            }

        return {

            "type":
                "SENSOR_DRIFT",

            "severity":
                self.fault.severity,

            "target_sensor":
                self.fault.target_sensor,

            "drift_value":
                self.fault.drift_value,
        }


    # ========================================================
    # ML LABEL
    # ========================================================

    def get_label(self) -> int:

        if self.fault.active:
            return 4

        return 0


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    model = (
        SensorFaultModel()
    )

    true_cht = 180.0

    print(
        "TRUE CHT:"
    )

    print(
        true_cht
    )

    print(
        "\nNORMAL SENSOR:"
    )

    print(
        model.apply(
            "CHT",
            true_cht
        )
    )

    model.activate_drift(

        target_sensor="CHT",

        drift_value=15.0,

        severity=0.80,
    )

    print(
        "\nSENSOR DRIFT:"
    )

    print(
        model.apply(
            "CHT",
            true_cht
        )
    )

    print(
        "\nFAULT:"
    )

    print(
        model.get_effect()
    )

    print(
        "\nML LABEL:"
    )

    print(
        model.get_label()
    )