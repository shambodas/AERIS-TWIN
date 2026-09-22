"""
AERIS-TWIN
Combustion Instability Fault Model

Purpose
-------
Model unstable / fluctuating combustion without completely
removing combustion from a cylinder.

Primary effects:

    - Combustion efficiency variation
    - Increased cycle-to-cycle variability
    - Increased vibration noise
    - Increased harmonic content
"""


from dataclasses import dataclass


@dataclass
class CombustionInstabilityFault:
    """
    Combustion instability state.
    """

    severity: float = 0.0

    active: bool = False


class CombustionInstabilityModel:
    """
    Generates a combustion-instability condition.

    severity:

        0.0 = stable combustion

        1.0 = severe instability
    """

    def __init__(self):

        self.fault = (
            CombustionInstabilityFault()
        )


    # ========================================================
    # ACTIVATE
    # ========================================================

    def activate(
        self,
        severity: float = 0.7,
    ):
        """
        Activate combustion instability.
        """

        self.fault = (
            CombustionInstabilityFault(

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
            CombustionInstabilityFault()
        )


    # ========================================================
    # STATUS
    # ========================================================

    def is_active(self) -> bool:

        return self.fault.active


    # ========================================================
    # COMBUSTION EFFECT
    # ========================================================

    def get_effect(self) -> dict:
        """
        Return combustion instability effects.
        """

        if not self.fault.active:

            return {

                "type": "NONE",

                "severity": 0.0,

                "efficiency_factor": 1.0,

                "instability_factor": 0.0,
            }

        severity = (
            self.fault.severity
        )

        efficiency_factor = (
            1.0
            - 0.15 * severity
        )

        instability_factor = (
            severity
        )

        return {

            "type":
                "COMBUSTION_INSTABILITY",

            "severity":
                severity,

            "efficiency_factor":
                efficiency_factor,

            "instability_factor":
                instability_factor,
        }


    # ========================================================
    # ML LABEL
    # ========================================================

    def get_label(self) -> int:

        if self.fault.active:
            return 3

        return 0


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    model = (
        CombustionInstabilityModel()
    )

    print(
        "NORMAL:"
    )

    print(
        model.get_effect()
    )

    model.activate(
        severity=0.85
    )

    print(
        "\nCOMBUSTION INSTABILITY:"
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