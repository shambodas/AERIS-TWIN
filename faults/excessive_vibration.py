"""
AERIS-TWIN
Excessive Vibration Fault Model

Purpose
-------
Model abnormal mechanical vibration without affecting 
combustion efficiency (e.g., loose mount, prop imbalance).

Primary effects:
    - Increased vibration noise and 1x harmonic content
"""

from dataclasses import dataclass

@dataclass
class ExcessiveVibrationFault:
    """
    Excessive vibration state.
    """
    severity: float = 0.0
    active: bool = False

class ExcessiveVibrationModel:
    """
    Generates an excessive-vibration condition.
    """
    def __init__(self):
        self.fault = ExcessiveVibrationFault()

    def activate(self, severity: float = 0.7):
        self.fault = ExcessiveVibrationFault(
            severity=max(0.0, min(1.0, float(severity))),
            active=True
        )

    def clear(self):
        self.fault = ExcessiveVibrationFault()

    def is_active(self) -> bool:
        return self.fault.active

    def get_effect(self) -> dict:
        if not self.fault.active: 
            return {}
        return {
            "type": "EXCESSIVE_VIBRATION",
            "severity": self.fault.severity
        }