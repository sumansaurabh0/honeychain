# Honey Chain SIH26021

Honey Chain connects real hive sensors to FastAPI, PostgreSQL, farmer health insight, hash-linked traceability, and public honey verification.

## Architecture

`ESP32 sensors -> Wi-Fi -> FastAPI -> PostgreSQL -> React farmer dashboard / public verification`

- `esp32/`: DHT11, HX711/load cell, MQ analog, and microphone firmware.
- `backend/`: FastAPI routes, SQLAlchemy models, health rules, and SHA-256 trace ledger.
- `frontend/`: Vite React landing page, farmer dashboard, trends, QR scanner, and `/verify/{batch_id}`.
- `simulator/`: normal and `--abnormal` sensor payload sender.

## Run locally

1. Set `DATABASE_URL` in `backend/.env`.
2. Install backend requirements and run from `backend/`:

   `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

3. Install frontend dependencies and run from `frontend/`:

   `npm install`
   `npm run dev`

Set `VITE_API_URL` for a deployed frontend. The development fallback is local-only; do not use it for production deployments.

Set `VITE_PUBLIC_APP_URL` to the deployed frontend origin when generating bottle QR images. Local development falls back to the current browser origin; ESP32 still requires the PC LAN IPv4 address rather than `localhost`.

## Authentication

Farmer registration creates a `PENDING` account. Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in the backend environment to provision the administrator once; do not commit these values. Set `FRONTEND_ORIGINS` to a comma-separated list of browser origins when using cookie sessions across deployments. Production cookies become secure when `ENVIRONMENT=production` or `COOKIE_SECURE=true`.

ESP32 and simulator sensor ingestion remains unauthenticated for compatibility with the existing device flow. Farmer batch, traceability, and ledger-anchor writes require a verified farmer session; public batch verification and QR routes remain open to consumers.

## Demo flow

- Create or use an existing hive such as `HIVE001`.
- Send a normal payload with `python simulator/simulator.py` or an abnormal payload with `python simulator/simulator.py --abnormal`.
- Open the farmer dashboard to view current readings, five real-history trends, health, and batch/trace forms.
- Create a batch and add processing, packaging, or distribution events.
- Open `/verify/{batch_id}` or scan a Honey Chain QR destination to verify the recorded journey and ledger integrity.
- From the farmer dashboard, create a batch to generate its real bottle QR image. The QR opens `/verify/{batch_id}`.

## ESP32

Use the tested pins: DHT11 GPIO4, HX711 DT GPIO18/SCK GPIO19, MQ AO GPIO39, microphone AO GPIO34, and calibration factor `248.9`. Replace only the local Wi-Fi and PC LAN server placeholders in the sketch. Never use `localhost` or `127.0.0.1` from the ESP32.

## Limitations

Farm registration is prototype-only because no registration persistence API exists. Camera QR scanning requires browser camera permission and a secure context such as localhost or HTTPS. Arduino/PlatformIO compilation and physical ESP32 testing require the hardware toolchain and device; they are not provided by this repository.
