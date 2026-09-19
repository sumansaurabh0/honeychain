import serial
import requests
import json

COM_PORT="COM7"
BAUD_RATE=115200
API_URL="http://127.0.0.1:8000/api/sensors"

def main():
    print("================================")
    print("HONEY CHAIN ESP32 BRIDGE")
    print("================================")
    print("Serial:",COM_PORT)
    print("API:",API_URL)
    print("Opening COM7...")

    try:
        ser=serial.Serial(COM_PORT,BAUD_RATE,timeout=2)
    except Exception as e:
        print("ERROR: Could not open COM7")
        print(e)
        return

    print("Connected to ESP32.")
    print("Waiting for sensor data...")

    try:
        while True:
            line=ser.readline().decode("utf-8",errors="ignore").strip()

            if not line:
                continue

            if not line.startswith("{"):
                continue

            try:
                data=json.loads(line)

                print()
                print("ESP32 DATA:")
                print(data)

                response=requests.post(
                    API_URL,
                    json=data,
                    timeout=5
                )

                print("FastAPI Response:",response.status_code)

                if response.text:
                    print("FastAPI:",response.text)

            except json.JSONDecodeError:
                print("Invalid JSON:",line)

            except requests.RequestException as e:
                print("FastAPI connection error:",e)

    except KeyboardInterrupt:
        print("\nBridge stopped.")

    finally:
        ser.close()

if __name__=="__main__":
    main()