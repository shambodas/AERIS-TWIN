"""
AERIS-TWIN
Misfire Fault Model

Purpose
-------
Generate a controlled cylinder-specific misfire condition.

Physical effects are passed to the engine models rather than
directly modifying engine states.

Primary effects:
    - Reduced combustion efficiency
    - Cylinder imbalance
    - Increased vibration
    - Reduced indicated work
"""


from dataclasses import dataclass


@dataclass
class MisfireFault:
    """
    Cylinder-specific misfire scenario.
    """

    target_cylinder: int = 3

    severity: float = 0.0

    active: bool = False


class MisfireModel:
    """
    Generates a physically meaningful misfire fault state.

    severity:
        0.0 = healthy
        1.0 = severe / continuous misfire
    """

    def __init__(
        self,
        num_cylinders: int = 4,
    ):

        if num_cylinders <= 0:
            raise ValueError(
                "Number of cylinders must be positive."
            )

        self.num_cylinders = num_cylinders

        self.fault = MisfireFault()


    # ========================================================
    # ACTIVATE
    # ========================================================

    def activate(
        self,
        severity: float = 0.8,
        target_cylinder: int = 3,
    ):
        """
        Activate misfire.
        """

        if not (
            1
            <= target_cylinder
            <= self.num_cylinders
        ):
            raise ValueError(
                f"target_cylinder must be between "
                f"1 and {self.num_cylinders}."
            )

        self.fault = MisfireFault(

            target_cylinder=target_cylinder,

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

        self.fault = MisfireFault()


    # ========================================================
    # STATUS
    # ========================================================

    def is_active(self) -> bool:

        return self.fault.active


    # ========================================================
    # ENGINE EFFECT
    # ========================================================

    def get_effect(self) -> dict:
        """
        Return fault information in a format that can be
        consumed by combustion.py and vibration.py.
        """

        if not self.fault.active:

            return {
                "type": "NONE",
                "severity": 0.0,
            }

        return {

            "type": "MISFIRE",

            "severity": (
                self.fault.severity
            ),

            "target_cylinder": (
                self.fault.target_cylinder
            ),
        }


    # ========================================================
    # ML LABEL
    # ========================================================

    def get_label(self) -> int:

        if self.fault.active:
            return 1

        return 0


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    model = MisfireModel(
        num_cylinders=4
    )

    print(
        "NORMAL:"
    )

    print(
        model.get_effect()
    )

    model.activate(
        severity=0.85,
        target_cylinder=3,
    )

    print(
        "\nMISFIRE:"
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