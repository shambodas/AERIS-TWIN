import re, json
with open('scratch_2.txt', 'r', encoding='utf-8') as f:
    text = f.read()

blocks = text.split('------------------------------------------------------------\nT+')
for b in blocks[1:]:
    time = b.split('s')[0]
    m = re.search(r'ENGINE HEALTH:\n(\{.*?\})\n\n(?:BLACK BOX|-----------------)', b, re.DOTALL)
    if not m:
        continue
    data = json.loads(m.group(1))
    eng = data['engine']
    tel = data['telemetry']
    intel = data['intelligence']
    ai = data['digital_twin']
    
    rpm = tel['rpm']
    throttle = eng['throttle_pct']
    load = eng['load_pct']
    cht = eng['cht_c']
    egt = eng['egt_c']
    oilt = eng['oil_temperature_c']
    oilp = eng['oil_pressure_psi']
    cht_dev = intel['features']['cht_deviation']
    egt_dev = intel['features']['egt_deviation']
    ai_fault = ai['ai_fault']
    conf = ai['ai_confidence']
    health = intel.get('health', {}).get('score', 'N/A')
    
    print(f'T+{time}s')
    print(f'  RPM: {rpm}, Throttle: {throttle}, Load: {load:.2f}%')
    print(f'  CHT: {cht:.1f}, EGT: {egt:.1f}, OilT: {oilt:.1f}, OilP: {oilp}')
    print(f'  Deviations -> CHT: {cht_dev:.1f}, EGT: {egt_dev:.1f}')
    print(f'  AI: {ai_fault} (Conf: {conf:.2f}), Health: {health}')
