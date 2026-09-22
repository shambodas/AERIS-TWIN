"""
AERIS-TWIN
Lubrication / oil-pressure fault model.

This fault represents degradation in the lubrication system that
reduces effective lubrication health and oil-pressure capability.
The engine lubrication model consumes the returned fault dictionary.
"""

from dataclasses import dataclass


@dataclass
class LubricationFault:
    severity: float = 0.0
    active: bool = False


class LubricationFaultModel:
    """Generate a controlled oil-pressure degradation condition."""

    def __init__(self):
        self.fault = LubricationFault()

    def activate(self, severity: float = 0.7):
        self.fault = LubricationFault(
            severity=max(0.0, min(1.0, float(severity))),
            active=True,
        )

    def clear(self):
        self.fault = LubricationFault()

    def is_active(self) -> bool:
        return self.fault.active

    def get_effect(self) -> dict:
        if not self.fault.active:
            return {
                "type": "NONE",
                "severity": 0.0,
            }

        return {
            "type": "LUBRICATION_DEGRADATION",
            "severity": self.fault.severity,
        }

    def get_label(self) -> int:
        return 5 if self.fault.active else 0
