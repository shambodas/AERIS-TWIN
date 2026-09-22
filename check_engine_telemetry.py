from dotenv import load_dotenv
import os
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
print("=== AERIS-TWIN ENGINE TELEMETRY ===")
print("RECORDS:", len(records))

fields = sorted(set(record.get_field() for record in records))
print("FIELDS:", fields)

if records:
    times = [record.get_time() for record in records]
    print("FIRST:", min(times))
    print("LAST:", max(times))
else:
    print("NO ENGINE TELEMETRY FOUND")

client.close()