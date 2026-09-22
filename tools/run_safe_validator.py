import time
import requests
import json
import os

SERVER_URL = "http://localhost:8080"
API_STATE = f"{SERVER_URL}/api/state"
API_COMMAND = f"{SERVER_URL}/api/command"
OUTPUT_FILE = r"C:\Users\sayan\aeris_twin\SIH_BLACK_BOX_VALIDATION.txt"

CASES = [
    "MISFIRE",
    "COOLING_DEGRADATION",
    "COMBUSTION_INSTABILITY",
    "SENSOR_DRIFT",
    "OIL_PRESSURE_DEGRADATION",
    "EXCESSIVE_VIBRATION",
    "INJECTOR_ABNORMALITY"
]

def command(cmd, params=None):
    if params is None:
        params = {}
    return requests.post(API_COMMAND, json={"command": cmd, "parameters": params})

def get_state():
    while True:
        try:
            resp = requests.get(API_STATE, timeout=2)
            if resp.status_code == 200:
                return resp.json()
        except:
            pass
        time.sleep(0.5)

def format_section(title, data):
    return f"{title}:\n{json.dumps(data, indent=2)}\n"

def write_report(lines):
    with open(OUTPUT_FILE, "a", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
        f.write("\n")

def get_backend_fault_state(state):
    dt = state.get("digital_twin", {})
    return dt.get("active_fault_name", ""), dt.get("fault_severity", 0.0)

def run():
    print("Starting SAFE validator...")
    summary_results = []
    
    for case_index, fault_name in enumerate(CASES):
        print(f"--- RUNNING CASE {case_index+1}: {fault_name} ---")
        report = []
        report.append("============================================================")
        report.append(f"CASE {case_index + 1} — {fault_name}")
        report.append("============================================================")
        
        # Absolute Rule 9: RESET BETWEEN CASES
        command("reset")
        time.sleep(2)
        
        # RESET VERIFICATION
        pre_start_state = get_state()
        uav_state = pre_start_state.get("uav", {}).get("status", "UNKNOWN")
        active_fault, severity = get_backend_fault_state(pre_start_state)
        
        if uav_state != "READY" or active_fault != "" or severity > 0.0:
            report.append("RESET VERIFICATION: FAILED")
            report.append(f"UAV STATE: {uav_state}")
            report.append(f"ACTIVE FAULT: {active_fault}")
            report.append(f"SEVERITY: {severity}")
            report.append("")
            
            report.append("-" * 60)
            report.append("CASE RESULT")
            report.append("-" * 60)
            report.append(f"Requested Fault:\n{fault_name}\n")
            report.append("Overall Result:\nRESET FAILED\n")
            
            write_report(report)
            summary_results.append({
                "case": fault_name, "verified": "-", "active": "-", 
                "t1": "-", "t5": "-", "t10": "-", "t15": "-", "t20": "-", 
                "ai": "N/A", "conf": "N/A", "health": "N/A", "class": "NOT VALIDATED", "overall": "RESET FAILED"
            })
            continue
            
        command("set_mission_route", {"route": ["Delhi", "Mumbai"]})
        time.sleep(1)
        
        pre_start_state = get_state()
        initial_alt = pre_start_state.get("digital_twin", {}).get("altitude_m")
        initial_alt_str = str(initial_alt) if initial_alt is not None else "N/A — field not exposed by API"
        initial_speed = pre_start_state.get("digital_twin", {}).get("airspeed_mps")
        initial_speed_str = str(initial_speed) if initial_speed is not None else "N/A — field not exposed by API"
        
        report.append("")
        report.append("FAULT REQUESTED:")
        report.append(fault_name)
        report.append("")
        report.append("MISSION:")
        report.append("Delhi → Mumbai")
        report.append("")
        report.append("INTERMEDIATE WAYPOINT:")
        report.append("NONE")
        report.append("")
        report.append("INITIAL ALTITUDE:")
        report.append(initial_alt_str)
        report.append("")
        report.append("INITIAL AIRSPEED:")
        report.append(initial_speed_str)
        report.append("")
        report.append("-" * 60)
        report.append("INITIAL PRE-START STATE")
        report.append("-" * 60)
        report.append("")
        report.append(json.dumps(pre_start_state, indent=2))
        report.append("")
        
        # Absolute Rule 1: Inject fault
        inject_req_fault = fault_name.lower()
        inject_resp = command("inject_fault", {"fault": inject_req_fault, "severity": 0.8})
        inject_status = inject_resp.status_code
        try:
            inject_json = inject_resp.json()
        except:
            inject_json = {"raw_text": inject_resp.text}
            
        time.sleep(1)
        
        post_inject_state = get_state()
        active_fault, severity = get_backend_fault_state(post_inject_state)
        
        # Verifying using authoritative state
        injection_verified = (active_fault.lower() == inject_req_fault and severity > 0.0)
        
        if not injection_verified:
            report.append("FAULT INJECTION VERIFICATION: FAILED")
            report.append("")
            report.append("EXPECTED FAULT:")
            report.append(fault_name)
            report.append("")
            report.append("BACKEND ACTIVE FAULT:")
            report.append(str(active_fault))
            report.append("")
            report.append("BACKEND FAULT SEVERITY:")
            report.append(str(severity))
            report.append("")
            report.append("INJECTION RESULT:")
            report.append("INJECTION FAILED")
            report.append("")
            report.append("AI CLASSIFICATION:")
            report.append("NOT VALIDATED")
            report.append("")
            report.append("OVERALL RESULT:")
            report.append("INJECTION FAILED")
            report.append("")
            
            # Case Result format
            report.append("-" * 60)
            report.append("CASE RESULT")
            report.append("-" * 60)
            report.append(f"Requested Fault:\n{fault_name}\n")
            report.append(f"Injection HTTP:\n{inject_status}\n")
            report.append(f"Injection Response:\n{json.dumps(inject_json)}\n")
            report.append("Injection Verification:\nFAIL\n")
            report.append(f"Backend Active Fault:\n{active_fault}\n")
            report.append(f"Backend Fault Severity:\n{severity}\n")
            report.append("Fault State Through Checkpoints:\nFAIL\n")
            report.append("AI Fault:\nN/A\n")
            report.append("AI Confidence:\nN/A\n")
            report.append("Health:\nN/A\n")
            report.append("Anomaly:\nN/A\n")
            report.append("Timing:\nN/A\n")
            report.append("Classification:\nNOT VALIDATED\n")
            report.append("Overall Result:\nINJECTION FAILED\n")
            
            write_report(report)
            summary_results.append({
                "case": fault_name, "verified": "FAIL", "active": "FAIL", 
                "t1": "-", "t5": "-", "t10": "-", "t15": "-", "t20": "-", 
                "ai": "N/A", "conf": "N/A", "health": "N/A", "class": "NOT VALIDATED", "overall": "INJECTION FAILED"
            })
            continue
            
        report.append("FAULT INJECTION VERIFIED")
        report.append("")
        
        # Absolute Rule 3: Start UAV
        command("start_uav")
        time.sleep(1)
        
        # START VERIFICATION
        start_state = get_state()
        uav_started_state = start_state.get("uav", {}).get("status", "UNKNOWN")
        
        if uav_started_state != "FLYING":
            report.append("START VERIFICATION: FAILED")
            report.append(f"UAV STATE: {uav_started_state}")
            report.append("")
            
            report.append("-" * 60)
            report.append("CASE RESULT")
            report.append("-" * 60)
            report.append(f"Requested Fault:\n{fault_name}\n")
            report.append(f"Injection Verification:\nPASS\n")
            report.append("Overall Result:\nSTART FAILED\n")
            
            write_report(report)
            summary_results.append({
                "case": fault_name, "verified": "PASS", "active": "-", 
                "t1": "-", "t5": "-", "t10": "-", "t15": "-", "t20": "-", 
                "ai": "N/A", "conf": "N/A", "health": "N/A", "class": "NOT VALIDATED", "overall": "START FAILED"
            })
            continue
        
        start_sim_time = start_state.get("digital_twin", {}).get("simulation_time_s", 0.0)
        
        active_fault, severity = get_backend_fault_state(start_state)
        fault_state_status = "PASS"
        if active_fault.lower() != inject_req_fault or severity <= 0.0:
            report.append("FAULT STATE LOST")
            fault_state_status = "LOST"
        
        checkpoints = [1.0, 5.0, 10.0, 15.0, 20.0]
        actual_sim_times = []
        final_state = start_state
        timing_pass = True
        
        chk_flags = {"t1": "-", "t5": "-", "t10": "-", "t15": "-", "t20": "-"}
        
        if fault_state_status == "PASS":
            for chk in checkpoints:
                target = start_sim_time + chk
                
                actual_sim = start_sim_time
                state = start_state
                
                # Checkpoint wait timeout (just in case sim freezes)
                timeout_start = time.time()
                timed_out = False
                
                while True:
                    state = get_state()
                    actual_sim = state.get("digital_twin", {}).get("simulation_time_s", 0.0)
                    if actual_sim >= target:
                        break
                    
                    if time.time() - timeout_start > 30: # 30s max wall clock wait for a checkpoint
                        timed_out = True
                        break
                        
                    time.sleep(0.5)
                    
                if timed_out:
                    timing_pass = False
                    break
                    
                actual_sim_times.append(actual_sim - start_sim_time)
                if chk == 20.0:
                    final_state = state
                    
                report.append("-" * 60)
                report.append(f"T+{int(chk)}s SIMULATION CHECKPOINT")
                report.append("-" * 60)
                report.append("")
                report.append("Requested Simulation Time:")
                report.append(f"T+{chk:.2f}s")
                report.append("")
                report.append("Actual Simulation Time:")
                report.append(f"T+{(actual_sim - start_sim_time):.2f}s")
                report.append("")
                
                # Absolute Rule 4: Verify fault at every checkpoint
                chk_active_fault, chk_severity = get_backend_fault_state(state)
                chk_ai_fault = state.get("intelligence", {}).get("fault_classification", {}).get("fault_type", "UNKNOWN")
                
                report.append("EXPECTED FAULT:")
                report.append(fault_name)
                report.append("BACKEND ACTIVE FAULT:")
                report.append(str(chk_active_fault))
                report.append("BACKEND FAULT SEVERITY:")
                report.append(str(chk_severity))
                report.append("AI FAULT:")
                report.append(str(chk_ai_fault))
                report.append("")
                
                # FAULT STATE LOSS MUST ABORT THE VALID TEST
                if chk_active_fault.lower() != inject_req_fault or chk_severity <= 0.0:
                    if chk_active_fault == "":
                        report.append("FAULT STATE LOST")
                        fault_state_status = "LOST"
                    else:
                        report.append("FAULT STATE MISMATCH")
                        fault_state_status = "MISMATCH"
                    timing_pass = False
                    break # Abort collection
                
                # Absolute Rule 7: Record the actual state
                gcs = {k: state.get(k) for k in ["uav", "mission", "flight_path", "telemetry_status"]}
                health_data = {k: state.get(k) for k in ["engine", "digital_twin", "telemetry", "intelligence"]}
                bbox = {k: state.get(k) for k in ["events", "alerts"]}
                
                report.append(format_section("GCS", gcs))
                report.append(format_section("ENGINE HEALTH", health_data))
                report.append(format_section("BLACK BOX", bbox))
                
                chk_flags[f"t{int(chk)}"] = "Y"
                
        # Final evaluation
        ai_fault = final_state.get("intelligence", {}).get("fault_classification", {}).get("fault_type", "UNKNOWN")
        ai_conf = final_state.get("intelligence", {}).get("fault_classification", {}).get("confidence", "UNKNOWN")
        ai_health = final_state.get("intelligence", {}).get("health", {}).get("score", "UNKNOWN")
        ai_anomaly = final_state.get("intelligence", {}).get("anomaly", {}).get("is_anomaly", "UNKNOWN")
        
        classification_result = "NOT VALIDATED"
        overall_result = "INJECTION FAILED"
        
        if not all(chk_flags[k] == "Y" for k in chk_flags):
            timing_pass = False
            
        # Absolute Rule 8: Classification PASS/FAIL
        if fault_state_status == "PASS":
            if ai_fault == fault_name:
                classification_result = "PASS"
                overall_result = "PASS"
            else:
                classification_result = "FAIL"
                overall_result = "AI CLASSIFICATION FAIL"
        elif fault_state_status == "LOST":
            overall_result = "FAULT STATE LOST"
        elif fault_state_status == "MISMATCH":
            overall_result = "FAULT STATE MISMATCH"
            
        report.append("-" * 60)
        report.append("CASE RESULT")
        report.append("-" * 60)
        report.append("")
        report.append("Requested Fault:")
        report.append(fault_name)
        report.append("")
        report.append("Injection HTTP:")
        report.append(str(inject_status))
        report.append("")
        report.append("Injection Response:")
        report.append(json.dumps(inject_json))
        report.append("")
        report.append("Injection Verification:")
        report.append("PASS")
        report.append("")
        report.append("Backend Active Fault:")
        report.append(str(active_fault))
        report.append("")
        report.append("Backend Fault Severity:")
        report.append(str(severity))
        report.append("")
        report.append("Fault State Through Checkpoints:")
        report.append(fault_state_status)
        report.append("")
        report.append("AI Fault:")
        report.append(str(ai_fault))
        report.append("")
        report.append("AI Confidence:")
        report.append(str(ai_conf))
        report.append("")
        report.append("Health:")
        report.append(str(ai_health))
        report.append("")
        report.append("Anomaly:")
        report.append(str(ai_anomaly))
        report.append("")
        report.append("Timing:")
        report.append("PASS" if timing_pass else "FAIL")
        report.append("")
        report.append("Classification:")
        report.append(classification_result)
        report.append("")
        report.append("Overall Result:")
        report.append(overall_result)
        report.append("")
        
        write_report(report)
        
        summary_results.append({
            "case": fault_name,
            "verified": "PASS",
            "active": fault_state_status,
            "t1": chk_flags["t1"],
            "t5": chk_flags["t5"],
            "t10": chk_flags["t10"],
            "t15": chk_flags["t15"],
            "t20": chk_flags["t20"],
            "ai": ai_fault if fault_state_status == "PASS" else "N/A",
            "conf": ai_conf if fault_state_status == "PASS" else "N/A",
            "health": ai_health if fault_state_status == "PASS" else "N/A",
            "class": classification_result,
            "overall": overall_result
        })

    summary = []
    summary.append("============================================================")
    summary.append("FINAL SIH BLACK-BOX VALIDATION SUMMARY")
    summary.append("============================================================")
    summary.append("")
    summary.append("| Case | Injection Verified | Fault Stayed Active | T+1 | T+5 | T+10 | T+15 | T+20 | AI Fault | Confidence | Health | Classification | Overall |")
    summary.append("|------|--------------------|---------------------|-----|-----|------|------|------|----------|------------|--------|----------------|---------|")
    
    num_injection_failed = 0
    num_validated = 0
    num_ai_fail = 0
    num_pass = 0
    num_lost = 0
    num_mismatch = 0
    num_start_failed = 0
    num_reset_failed = 0
    
    for r in summary_results:
        summary.append(f"| {r['case']} | {r['verified']} | {r['active']} | {r['t1']} | {r['t5']} | {r['t10']} | {r['t15']} | {r['t20']} | {r['ai']} | {r['conf']} | {r['health']} | {r['class']} | {r['overall']} |")
        if r['overall'] == "INJECTION FAILED":
            num_injection_failed += 1
        elif r['overall'] == "AI CLASSIFICATION FAIL":
            num_validated += 1
            num_ai_fail += 1
        elif r['overall'] == "PASS":
            num_validated += 1
            num_pass += 1
        elif r['overall'] == "FAULT STATE LOST":
            num_lost += 1
        elif r['overall'] == "FAULT STATE MISMATCH":
            num_mismatch += 1
        elif r['overall'] == "START FAILED":
            num_start_failed += 1
        elif r['overall'] == "RESET FAILED":
            num_reset_failed += 1
            
    summary.append("")
    summary.append(f"{num_injection_failed} INJECTION FAILED")
    summary.append(f"{num_start_failed} START FAILED")
    summary.append(f"{num_reset_failed} RESET FAILED")
    summary.append(f"{num_validated} VALIDATED")
    summary.append(f"{num_ai_fail} AI CLASSIFICATION FAIL")
    summary.append(f"{num_pass} PASS")
    summary.append(f"{num_lost} FAULT STATE LOST")
    summary.append(f"{num_mismatch} FAULT STATE MISMATCH")
    summary.append("")
    
    write_report(summary)

if __name__ == "__main__":
    run()
