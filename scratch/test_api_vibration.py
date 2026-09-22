
import requests
import json
import time

response = requests.post('http://localhost:8080/api/fault/inject', json={
    'fault': 'excessive_vibration',
    'severity': 0.8
})
print('Fault injected:', response.json())

time.sleep(10)  # Wait for fault to propagate

response = requests.get('http://localhost:8080/api/state')
print('State after 10s:')
print(json.dumps(response.json()['intelligence'], indent=2))

