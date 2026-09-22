"""
AERIS-TWIN
Cooling System Fault Model

Purpose
-------
Generate controlled degradation of engine cooling capability.

Primary physical effect:

    Cooling efficiency ↓
            ↓
    Heat rejection ↓
            ↓
    CHT / EGT / Oil temperature ↑

This fault is primarily consumed by thermal.py.
"""


from dataclasses import dataclass


@dataclass
class CoolingFault:
    """
    Cooling degradation state.
    """

    severity: float = 0.0

    active: bool = False


class CoolingFaultModel:
    """
    Cooling degradation model.

    severity:

        0.0 = healthy cooling

        1.0 = severe cooling degradation
    """

    def __init__(self):

        self.fault = CoolingFault()


    # ========================================================
    # ACTIVATE
    # ========================================================

    def activate(
        self,
        severity: float = 0.7,
    ):
        """
        Activate cooling degradation.
        """

        self.fault = CoolingFault(

            severity=max(
                0.0,
                min(
                    1.0,
                    float(severity)
                )
            ),

            active=True,
        )


    # ========================================================
    # CLEAR
    # ========================================================

    def clear(self):

        self.fault = CoolingFault()


    # ========================================================
    # STATUS
    # ========================================================

    def is_active(self) -> bool:

        return self.fault.active


    # ========================================================
    # THERMAL EFFECT
    # ========================================================

    def get_effect(self) -> dict:
        """
        Return cooling-system degradation effect.

        cooling_factor:

            1.0 = normal cooling

            0.5 = severe degradation
        """

        if not self.fault.active:

            return {

                "type": "NONE",

                "severity": 0.0,

                "cooling_factor": 1.0,
            }

        cooling_factor = (
            1.0
            - 0.50
            * self.fault.severity
        )

        return {

            "type":
                "COOLING_DEGRADATION",

            "severity":
                self.fault.severity,

            "cooling_factor":
                cooling_factor,
        }


    # ========================================================
    # ML LABEL
    # ========================================================

    def get_label(self) -> int:

        if self.fault.active:
            return 2

        return 0


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    model = (
        CoolingFaultModel()
    )

    print(
        "NORMAL:"
    )

    print(
        model.get_effect()
    )

    model.activate(
        severity=0.80
    )

    print(
        "\nCOOLING DEGRADATION:"
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