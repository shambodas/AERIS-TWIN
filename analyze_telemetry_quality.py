from dotenv import load_dotenv
import os
from collections import Counter
from influxdb_client import InfluxDBClient

load_dotenv()

client = InfluxDBClient(
    url=os.getenv("INFLUXDB_URL"),
    token=os.getenv("INFLUXDB_TOKEN"),
    org=os.getenv("INFLUXDB_ORG"),
)

bucket = os.getenv("INFLUXDB_BUCKET")

query = f'''
from(bucket: "{bucket}")
  |> range(start: -30m)
  |> filter(fn: (r) => r._measurement == "engine_telemetry")
'''

tables = client.query_api().query(query)

records = [record for table in tables for record in table.records]

print()
print("=== AERIS-TWIN TELEMETRY QUALITY AUDIT ===")
print("TOTAL FIELD RECORDS:", len(records))

timestamps = Counter(record.get_time() for record in records)

print("UNIQUE TIMESTAMPS:", len(timestamps))

if timestamps:
    counts = Counter(timestamps.values())

    print()
    print("FIELDS PER TIMESTAMP:")
    for count, occurrences in sorted(counts.items()):
        print(f"  {count} fields: {occurrences} timestamps")

    times = sorted(timestamps.keys())

    intervals = [
        (times[i] - times[i-1]).total_seconds()
        for i in range(1, len(times))
    ]

    if intervals:
        print()
        print("TIMESTAMP INTERVAL:")
        print("  MIN:", min(intervals), "seconds")
        print("  MAX:", max(intervals), "seconds")
        print("  AVG:", sum(intervals) / len(intervals), "seconds")

        expected = 1.0
        irregular = [
            x for x in intervals
            if abs(x - expected) > 0.25
        ]

        print("  IRREGULAR INTERVALS:", len(irregular))

    print()
    print("FIRST TIMESTAMP:", times[0])
    print("LAST TIMESTAMP:", times[-1])

print()
print("=== FIELD COUNTS ===")

field_counts = Counter(record.get_field() for record in records)

for field, count in sorted(field_counts.items()):
    print(f"{field}: {count}")

client.close()