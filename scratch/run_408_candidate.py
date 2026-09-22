import os
import shutil
import subprocess
import time
import sys

prod_model = 'ml/model_artifacts/fault_classifier.pkl'
backup_model = 'ml/model_artifacts/fault_classifier_backup.pkl'
candidate_model = 'ml/model_artifacts/fault_classifier_hybrid_candidate.pkl'

print("=== STARTING 408 VALIDATOR PIPELINE ===")

if not os.path.exists(candidate_model):
    print("Error: Candidate model not found!")
    sys.exit(1)

print(f"Backing up {prod_model} to {backup_model}...")
shutil.copy(prod_model, backup_model)

print(f"Copying {candidate_model} to {prod_model}...")
shutil.copy(candidate_model, prod_model)

try:
    print("Starting server.py in background...")
    # Start server
    server_proc = subprocess.Popen([sys.executable, "server.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Wait for server to start
    print("Waiting for server to initialize (5s)...")
    time.sleep(5)
    
    print("Running 408 validator...")
    # Run validator
    validator_proc = subprocess.run([sys.executable, "tools/fresh_408_validator.py"], capture_output=True, text=True)
    
    print("\n--- VALIDATOR OUTPUT ---")
    print(validator_proc.stdout)
    if validator_proc.stderr:
        print("\n--- VALIDATOR STDERR ---")
        print(validator_proc.stderr)
        
finally:
    print("\nShutting down server...")
    server_proc.terminate()
    try:
        server_proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        server_proc.kill()
        
    print("Restoring production model...")
    shutil.copy(backup_model, prod_model)
    os.remove(backup_model)
    print("=== PIPELINE FINISHED ===")
