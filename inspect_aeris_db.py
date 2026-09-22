from dotenv import load_dotenv
import os
from influxdb_client import InfluxDBClient

load_dotenv()

client = InfluxDBClient(
    url=os.getenv("INFLUXDB_URL"),
    token=os.getenv("INFLUXDB_TOKEN"),
    org=os.getenv("INFLUXDB_ORG")
)

bucket = os.getenv("INFLUXDB_BUCKET")

query = f'''
from(bucket: "{bucket}")
  |> range(start: -30m)
  |> filter(fn: (r) => exists r._value)
  |> keep(columns: ["_time", "_measurement", "_field", "_value"])
'''

try:
    tables = client.query_api().query(query)

    records = []

    for table in tables:
        for record in table.records:
            records.append(record)

    print("\n=== DATABASE TELEMETRY AUDIT ===")
    print("Total records:", len(records))

    measurements = sorted(set(r.get_measurement() for r in records))

    print("\nMeasurements:")
    for m in measurements:
        print(" -", m)

    print("\nField counts:")
    fields = {}
    for r in records:
        fields[r.get_field()] = fields.get(r.get_field(), 0) + 1

    for field, count in sorted(fields.items()):
        print(f" - {field}: {count}")

    print("\nLast 20 records:")
    for r in sorted(records, key=lambda x: x.get_time())[-20:]:
        print(
            r.get_time(),
            "|",
            r.get_measurement(),
            "|",
            r.get_field(),
            "|",
            r.get_value()
        )

finally:
    client.close()