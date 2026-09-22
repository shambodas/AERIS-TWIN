"""
AERIS-TWIN
Engine Injection Timing Model

Purpose
-------
Calculate a deterministic nominal injection timing based on engine
operating conditions, and apply a severity-scaled timing retard for
INJECTOR_ABNORMALITY on the prototype affected cylinder.

IMPORTANT — SIMULATION ASSUMPTIONS
------------------------------------
The coefficients used here are engineering-estimate prototype constants
for a generic four-cylinder aviation piston engine. They are NOT
calibrated from real Rotax or any other manufacturer data.

    T_BASE   = 10.0 degrees BTDC
    K_RPM    = 0.003 degrees / RPM
    K_LOAD   = -0.02 degrees / % throttle

    Maximum advance bound:  22.0 degrees BTDC
    Minimum advance bound:   4.0 degrees BTDC

Affected cylinder for INJECTOR_ABNORMALITY:
    Cylinder index 1 (first cylinder) is used as the deterministic
    PROTOTYPE affected cylinder. This is a simulation simplification.
    The actual InjectorAbnormalityModel does not yet carry a per-cylinder
    identity; cylinder 1 is not a real engine-specific calibration fact.

Timing retard for INJECTOR_ABNORMALITY:
    Modelled as injector opening lag / stiction causing a retarded
    (negative/reduced-advance) deviation proportional to severity.
    Maximum retard at severity = 1.0: 6.0 degrees.

Fault coupling (as specified):
    INJECTOR_ABNORMALITY     -> severity-scaled retard on cylinder 1
    NORMAL                   -> zero deviation
    MISFIRE                  -> zero timing deviation (combustion failure, not timing)
    COMBUSTION_INSTABILITY   -> zero sustained timing offset
    SENSOR_DRIFT             -> true physical timing unchanged
    COOLING_DEGRADATION      -> no direct timing change
    OIL_PRESSURE_DEGRADATION -> no direct timing change
    EXCESSIVE_VIBRATION      -> no direct timing change
"""

from dataclasses import dataclass


# ============================================================
# PROTOTYPE CONSTANTS — NOT MANUFACTURER CALIBRATION VALUES
# ============================================================

#: Base timing advance at idle conditions [degrees BTDC]
T_BASE_DEG = 10.0

#: Timing advance coefficient for RPM [degrees / RPM]
K_RPM = 0.003

#: Timing advance coefficient for throttle [degrees / % throttle]
K_LOAD = -0.02

#: Absolute maximum timing advance [degrees BTDC]
TIMING_MAX_DEG = 22.0

#: Absolute minimum timing advance [degrees BTDC]
TIMING_MIN_DEG = 4.0

#: Maximum timing retard applied by INJECTOR_ABNORMALITY at severity 1.0 [degrees]
MAX_INJECTOR_RETARD_DEG = 6.0

#: Prototype affected cylinder (1-based). Cylinder 1 is a simulation assumption.
PROTOTYPE_AFFECTED_CYLINDER = 1


# ============================================================
# DATA STRUCTURE
# ============================================================

@dataclass
class InjectionTimingState:
    """
    Injection timing state for one simulation step.

    All angles are in degrees BTDC (Before Top Dead Centre).
    Positive values = more advanced.
    Negative deviation = retarded relative to nominal.
    """

    #: Nominal (physics-ideal) injection timing [degrees BTDC]
    injection_timing_nominal_deg: float

    #: Actual injection timing accounting for fault effects [degrees BTDC]
    injection_timing_actual_deg: float

    #: Deviation from nominal (actual - nominal) [degrees]
    injection_timing_deviation_deg: float

    #: Prototype affected cylinder (1-based index, or 0 if none)
    affected_cylinder: int


# ============================================================
# INJECTION TIMING MODEL
# ============================================================

class InjectionTimingModel:
    """
    Deterministic nominal injection timing model.

    Nominal timing is a function of RPM and throttle position.
    INJECTOR_ABNORMALITY applies a severity-scaled retard to
    the prototype affected cylinder (cylinder 1).

    All other fault types produce zero timing deviation.
    """

    @staticmethod
    def calculate_nominal(rpm: float, throttle_pct: float) -> float:
        """
        Calculate nominal injection timing advance.

        Parameters
        ----------
        rpm : float
            Engine speed [RPM].
        throttle_pct : float
            Throttle position [%].

        Returns
        -------
        float
            Nominal timing [degrees BTDC].
        """
        rpm = max(0.0, rpm)
        throttle_pct = max(0.0, min(100.0, throttle_pct))
        timing = T_BASE_DEG + K_RPM * rpm + K_LOAD * throttle_pct
        return max(TIMING_MIN_DEG, min(TIMING_MAX_DEG, timing))

    def calculate(
        self,
        rpm: float,
        throttle_pct: float,
        fault_state=None,
    ) -> InjectionTimingState:
        """
        Calculate injection timing for the current simulation step.

        Parameters
        ----------
        rpm : float
            Engine speed [RPM].
        throttle_pct : float
            Throttle position [%].
        fault_state : dict or None
            Active physical fault dict from the simulator.
            Expected keys: 'type' (str), 'severity' (float).

        Returns
        -------
        InjectionTimingState
        """
        nominal = self.calculate_nominal(rpm, throttle_pct)

        actual = nominal
        deviation = 0.0
        affected_cylinder = 0

        if fault_state:
            fault_type = str(fault_state.get("type", "")).upper()
            severity = float(fault_state.get("severity", 0.0))
            severity = max(0.0, min(1.0, severity))

            if fault_type == "INJECTOR_ABNORMALITY" and severity > 0.0:
                # Severity-scaled retard on prototype cylinder 1.
                # Modelled as injector opening lag / stiction.
                retard = MAX_INJECTOR_RETARD_DEG * severity
                actual = max(TIMING_MIN_DEG, nominal - retard)
                deviation = actual - nominal   # negative = retarded
                affected_cylinder = PROTOTYPE_AFFECTED_CYLINDER

            # All other fault types: no timing deviation.
            # MISFIRE, COMBUSTION_INSTABILITY, SENSOR_DRIFT,
            # COOLING_DEGRADATION, OIL_PRESSURE_DEGRADATION,
            # EXCESSIVE_VIBRATION -> actual = nominal, deviation = 0.

        return InjectionTimingState(
            injection_timing_nominal_deg=round(nominal, 3),
            injection_timing_actual_deg=round(actual, 3),
            injection_timing_deviation_deg=round(deviation, 3),
            affected_cylinder=affected_cylinder,
        )
