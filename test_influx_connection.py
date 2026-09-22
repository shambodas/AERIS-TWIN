import os
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient

load_dotenv()

url = os.getenv("INFLUXDB_URL")
token = os.getenv("INFLUXDB_TOKEN")
org = os.getenv("INFLUXDB_ORG")
bucket = os.getenv("INFLUXDB_BUCKET")

print("URL:", url)
print("ORG:", org)
print("BUCKET:", bucket)

if not token:
    print("ERROR: Token was not loaded from .env")
    exit()

client = InfluxDBClient(
    url=url,
    token=token,
    org=org
)

print("Connection successful:", client.ping())

client.close()