"""Send the fixed ESP32 payload to Honey Chain."""
import json, sys
from urllib.request import Request, urlopen

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/api/sensors"
payload = {"hive_id":"HIVE001","temperature":27.1,"humidity":54.0,"weight":118.5,"gas_raw":2186,"mic_raw":1733}
if "--abnormal" in sys.argv: payload.update(temperature=39.0, humidity=30.0, gas_raw=3001, mic_raw=3100)
request = Request(URL, data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"}, method="POST")
with urlopen(request) as response: print(response.read().decode())
