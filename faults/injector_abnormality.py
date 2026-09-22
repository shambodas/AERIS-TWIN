"""
AERIS-TWIN
Injector Abnormality Fault Model

Purpose
-------
Model a lean/restricted injector on a single cylinder.

Primary effects:
    - Reduced fuel flow to affected cylinder
    - Reduced combustion efficiency
    - Moderate EGT increase
"""

from dataclasses import dataclass

@dataclass
class InjectorAbnormalityFault:
    """
    Injector abnormality state.
    """
    severity: float = 0.0
    active: bool = False

class InjectorAbnormalityModel:
    """
    Generates an injector abnormality condition.
    """
    def __init__(self):
        self.fault = InjectorAbnormalityFault()

    def activate(self, severity: float = 0.7):
        self.fault = InjectorAbnormalityFault(
            severity=max(0.0, min(1.0, float(severity))),
            active=True
        )

    def clear(self):
        self.fault = InjectorAbnormalityFault()

    def is_active(self) -> bool:
        return self.fault.active

    def get_effect(self) -> dict:
        if not self.fault.active: 
            return {}
        return {
            "type": "INJECTOR_ABNORMALITY",
            "severity": self.fault.severity
        }
