
from intelligence.diagnostics import DiagnosticGenerator

generator = DiagnosticGenerator()

deviations = {
    'cht_deviation': {'absolute': 10.5, 'normalized': 0.73},
    'vibration_deviation': {'absolute': 0.8, 'normalized': 6.94}
}

result = generator.build(
    fault_type='EXCESSIVE_VIBRATION',
    severity='CRITICAL',
    anomaly_score=0.60,
    confidence=0.867,
    deviations=deviations,
    sensor_summary={}
)

print('--- EXCESSIVE_VIBRATION ---')
print('Title:', result['title'])
print('Interpretation:', result['interpretation'])
print('Recommended:', result['recommended_action'])
print('Evidence:')
for e in result['evidence']:
    print(' -', e)

result_normal = generator.build(
    fault_type='NORMAL',
    severity='NORMAL',
    anomaly_score=0.1,
    confidence=0.99,
    deviations={},
    sensor_summary={}
)

print('\n--- NORMAL ---')
print('Title:', result_normal['title'])
print('Interpretation:', result_normal['interpretation'])
print('Recommended:', result_normal['recommended_action'])

