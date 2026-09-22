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
  |> filter(fn: (r) => r._measurement == "flight_records")
'''

tables = client.query_api().query(query)

records = [record for table in tables for record in table.records]

print()
print("=== AERIS-TWIN FLIGHT RECORD AUDIT ===")
print("TOTAL RECORDS:", len(records))

for record in records:
    print(
        record.get_time(),
        "| FIELD:", record.get_field(),
        "| VALUE:", record.get_value()
    )

client.close()