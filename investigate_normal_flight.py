"""
AERIS-TWIN — Normal-Flight False-Critical Investigation
=======================================================
Starts a fresh mission, polls the live server at 1-second intervals,
and records the complete intelligence output at each tick.

Checks for false positives:
  - health = 0
  - fault != NORMAL during normal flight
  - severity = CRITICAL/SEVERE during normal flight

Also exercises the physics_expectation model directly over the full
operating envelope (800 – 6000 RPM) to surface any calibration issues.
"""
from __future__ import annotations
import sys
import time
import json
import math
import requests

BASE = "http://localhost:8080"
TIMEOUT = 4

def get(path):
    return requests.get(f"{BASE}{path}", timeout=TIMEOUT).json()

def post(path, body):
    return requests.post(f"{BASE}{path}", json=body, timeout=TIMEOUT).json()


# ──────────────────────────────────────────────────────────────
# PART A — Physics-Expectation Model Calibration Sweep
# (no server needed for this part)
# ──────────────────────────────────────────────────────────────
def sweep_expectation_model():
    sys.path.insert(0, ".")
    from intelligence.physics_expectation import PhysicsExpectationEngine
    engine = PhysicsExpectationEngine()

    print("\n" + "=" * 72)
    print("PART A — PHYSICS EXPECTATION MODEL CALIBRATION SWEEP")
    print("=" * 72)
    header = f"{'RPM':>7} {'Thr%':>5} {'Alt':>6} | {'ExpOilP':>8} {'ExpCHT':>7} {'ExpEGT':>7} {'ExpOilT':>7} {'ExpVib':>7}"
    print(header)
    print("-" * 72)

    issues = []
    test_points = [
        # (rpm, throttle, altitude_m, time_s, ambient_c)
        (800,  5,  0,    5,  20),   # GROUND IDLE
        (1500, 20, 0,    15, 20),   # LOW POWER
        (3000, 45, 1500, 30, 15),   # MEDIUM
        (4000, 65, 2500, 50, 10),   # MEDIUM-HIGH
        (5000, 80, 3500, 70, 5),    # CLIMB
        (6000, 95, 4000, 90, 2),    # MAX CRUISE
    ]
    for rpm, thr, alt, t, amb in test_points:
        op = {"rpm": rpm, "throttle_pct": thr, "altitude_m": alt,
              "time_s": t, "ambient_temperature_c": amb}
        exp = engine.calculate(operating_state=op)
        oil_p = exp["expected_oil_pressure"]
        cht   = exp["expected_cht"]
        egt   = exp["expected_egt"]
        oil_t = exp["expected_oil_temperature"]
        vib   = exp["expected_vibration"]
        print(f"{rpm:>7} {thr:>5} {alt:>6} | {oil_p:>8.1f} {cht:>7.1f} {egt:>7.1f} {oil_t:>7.1f} {vib:>7.4f}")

        # Physics sanity checks
        if oil_p < 20:
            issues.append(f"  [WARN] RPM={rpm}: expected_oil_pressure={oil_p:.1f} psi — below 20 psi floor (CRITICAL threshold)")
        if oil_p < 0:
            issues.append(f"  [FAIL] RPM={rpm}: expected_oil_pressure={oil_p:.1f} psi — NEGATIVE (impossible)")
        if cht < 50 or cht > 500:
            issues.append(f"  [WARN] RPM={rpm}: expected_cht={cht:.1f} C — outside plausible range [50-500]")
        if egt < 100 or egt > 1000:
            issues.append(f"  [WARN] RPM={rpm}: expected_egt={egt:.1f} C — outside plausible range [100-1000]")
        if oil_t < 40 or oil_t > 200:
            issues.append(f"  [WARN] RPM={rpm}: expected_oil_temperature={oil_t:.1f} C — outside plausible range [40-200]")

    if issues:
        print()
        print("CALIBRATION ISSUES FOUND:")
        for issue in issues:
            print(issue)
    else:
        print("\n[OK] All expectation values are within plausible engineering ranges.")
    return issues


# ──────────────────────────────────────────────────────────────
# PART B — Live Normal-Flight Monitoring Pass
# ──────────────────────────────────────────────────────────────
def live_normal_flight_test():
    print("\n" + "=" * 72)
    print("PART B — LIVE NORMAL-FLIGHT MONITORING PASS")
    print("=" * 72)

    # Reset to clean state
    print("[*] Resetting simulation to clean state...")
    post("/api/command", {"command": "reset"})
    time.sleep(0.5)

    # Start normal mission (no fault)
    print("[*] Starting mission: cruise_isr, Delhi -> Jaipur -> Jodhpur ...")
    post("/api/command", {
        "command": "start_mission",
        "parameters": {
            "mission": "cruise_isr",
            "route": ["Delhi", "Jaipur", "Jodhpur"]
        }
    })
    time.sleep(1.0)

    records = []
    false_positives = []
    SAMPLE_DURATION = 90   # seconds of real-time sampling
    POLL_INTERVAL  = 1.0   # seconds between polls

    print(f"[*] Sampling for {SAMPLE_DURATION}s at {1/POLL_INTERVAL:.0f} Hz ...")
    print()

    hdr = (f"{'t_sim':>7} {'RPM':>6} {'Thr':>5} {'Alt':>6} | "
           f"{'OilP':>6} {'EXP_OP':>7} {'DEV_OP':>7} | "
           f"{'CHT':>6} {'EXP_C':>7} {'DEV_C':>7} | "
           f"{'Hlth':>5} {'Sev':<10} {'Fault':<24}")
    print(hdr)
    print("-" * 120)

    start = time.time()
    poll_count = 0
    while time.time() - start < SAMPLE_DURATION:
        try:
            state = get("/api/state")
        except Exception as exc:
            print(f"  [ERROR] Could not poll /api/state: {exc}")
            time.sleep(POLL_INTERVAL)
            continue

        # ── extract fields ────────────────────────────────────
        uav       = state.get("uav", {})
        eng       = state.get("engine", {})
        dt        = state.get("digital_twin", {})
        intel     = state.get("intelligence", {})
        mission   = state.get("mission", {})

        t_sim     = float(dt.get("simulation_time_s", 0))
        rpm       = float(eng.get("rpm", 0))
        thr       = float(eng.get("throttle_pct", 0))
        alt       = float(uav.get("altitude_m", 0))
        oil_p     = float(eng.get("oil_pressure_psi", 0))
        cht       = float(eng.get("cht_c", 0))
        health    = float(dt.get("health_pct", 0))
        severity  = str(dt.get("ai_severity", "?"))
        ai_fault  = str(dt.get("ai_fault", "?"))
        phase     = str(mission.get("phase", "?"))
        flight_st = str(uav.get("status", "?"))

        expected  = intel.get("expected", {})
        deviations= intel.get("deviations", {})
        exp_op    = float(expected.get("expected_oil_pressure", -1))
        dev_op    = float(deviations.get("oil_pressure_deviation", {}).get("absolute", 999))
        exp_cht   = float(expected.get("expected_cht", -1))
        dev_cht   = float(deviations.get("cht_deviation", {}).get("absolute", 999))

        row = (f"{t_sim:>7.1f} {rpm:>6.0f} {thr:>5.1f} {alt:>6.0f} | "
               f"{oil_p:>6.1f} {exp_op:>7.1f} {dev_op:>+7.1f} | "
               f"{cht:>6.1f} {exp_cht:>7.1f} {dev_cht:>+7.1f} | "
               f"{health:>5.1f} {severity:<10} {ai_fault:<24}")
        print(row)

        records.append({
            "t_sim": t_sim, "rpm": rpm, "throttle": thr, "alt": alt,
            "oil_pressure": oil_p, "expected_oil_pressure": exp_op,
            "oil_pressure_dev": dev_op, "cht": cht, "expected_cht": exp_cht,
            "cht_dev": dev_cht, "health": health, "severity": severity,
            "ai_fault": ai_fault, "phase": phase, "flight_state": flight_st,
        })

        # Detect false positives
        if health == 0 or severity in ("CRITICAL", "SEVERE"):
            false_positives.append({
                "t_sim": t_sim, "rpm": rpm, "health": health,
                "severity": severity, "ai_fault": ai_fault,
                "oil_pressure_dev": dev_op, "cht_dev": dev_cht,
            })

        poll_count += 1
        time.sleep(POLL_INTERVAL)

    print("-" * 120)
    print(f"[*] Sampled {poll_count} points over {SAMPLE_DURATION}s of real time.")

    # ── Summary ────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    if not records:
        print("[FAIL] No records collected.")
        return False

    min_health = min(r["health"] for r in records)
    max_health = max(r["health"] for r in records)
    min_oil    = min(r["oil_pressure"] for r in records)
    max_oil    = max(r["oil_pressure"] for r in records)
    severities = set(r["severity"] for r in records)
    faults     = set(r["ai_fault"] for r in records)

    print(f"  Health range:      {min_health:.1f} – {max_health:.1f}")
    print(f"  Oil pressure:      {min_oil:.1f} – {max_oil:.1f} psi")
    print(f"  Severity levels:   {severities}")
    print(f"  Fault types seen:  {faults}")
    print(f"  False positives:   {len(false_positives)}")

    print()
    if false_positives:
        print("FALSE-POSITIVE RECORDS (health=0 or CRITICAL/SEVERE during NORMAL FLIGHT):")
        for fp in false_positives:
            print(f"  t={fp['t_sim']:.1f}s  RPM={fp['rpm']:.0f}  health={fp['health']}  "
                  f"severity={fp['severity']}  fault={fp['ai_fault']}  "
                  f"oil_dev={fp['oil_pressure_dev']:+.1f}  cht_dev={fp['cht_dev']:+.1f}")
        print()
        print("[FAIL] Normal flight produced false-critical/false-fault states.")
        return False
    else:
        print("[PASS] No false-critical or false-fault states during normal flight.")
        return True


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\nAERIS-TWIN — Normal-Flight False-Critical Investigation")
    print("=" * 72)

    calibration_issues = sweep_expectation_model()

    try:
        live_pass = live_normal_flight_test()
    except Exception as exc:
        print(f"\n[FATAL] Live test failed: {exc}")
        import traceback; traceback.print_exc()
        live_pass = False

    print("\n" + "=" * 72)
    print("FINAL VERDICT")
    print("=" * 72)
    print(f"  Calibration issues:  {'NONE' if not calibration_issues else str(len(calibration_issues)) + ' issues'}")
    print(f"  Live flight test:    {'PASS' if live_pass else 'FAIL'}")
    overall = not calibration_issues and live_pass
    print(f"  Overall:             {'PASS' if overall else 'FAIL'}")
    sys.exit(0 if overall else 1)
