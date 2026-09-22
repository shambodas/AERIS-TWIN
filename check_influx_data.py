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
import "influxdata/influxdb/schema"

schema.measurements(
    bucket: "{bucket}",
    start: -30m
)
'''

try:
    tables = client.query_api().query(query)

    measurements = []

    for table in tables:
        for record in table.records:
            measurements.append(record.get_value())

    print("\n=== MEASUREMENTS IN AERIS-TWIN BUCKET ===")
    for measurement in sorted(set(measurements)):
        print(measurement)

    print("\nTOTAL UNIQUE MEASUREMENTS:", len(set(measurements)))

finally:
    client.close()