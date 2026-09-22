import serial
import serial.tools.list_ports
import requests
import json

BAUD_RATE=115200
API_URL="https://honey-chain-backend-tjvt.onrender.com/api/sensors"


def find_esp32():
    for port in serial.tools.list_ports.comports():
        text=f"{port.description} {port.manufacturer} {port.product}".lower()

        if any(x in text for x in ["esp32","cp210","ch340","wch"]):
            return port.device

    return None


COM_PORT=find_esp32()

if not COM_PORT:
    raise RuntimeError("ESP32 not found. Connect the ESP32 and try again.")


def main():
    print("================================")
    print("HONEY CHAIN ESP32 BRIDGE")
    print("================================")
    print("ESP32 detected on:",COM_PORT)
    print("Serial:",COM_PORT)
    print("API:",API_URL)
    print("Opening",COM_PORT,"...")

    try:
        ser=serial.Serial(COM_PORT,BAUD_RATE,timeout=2)
    except Exception as e:
        print(f"ERROR: Could not open {COM_PORT}")
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