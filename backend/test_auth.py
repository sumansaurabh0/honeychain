import atexit
import os
import shutil
import tempfile
from pathlib import Path

TEST_ROOT = Path(tempfile.mkdtemp(prefix="honey-chain-auth-"))
atexit.register(shutil.rmtree, TEST_ROOT, ignore_errors=True)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'auth.db'}"
os.environ["ADMIN_EMAIL"] = "admin@test.local"
os.environ["ADMIN_PASSWORD"] = "TestAdmin!123"
os.environ["COOKIE_SECURE"] = "false"

from fastapi.testclient import TestClient

from backend.main import HoneyBatch, SessionLocal, app


def register(client, *, email, farmer_id, password="StrongPass!123"):
    return client.post(
        "/api/auth/register",
        json={
            "full_name": "Demo Farmer",
            "email": email,
            "phone": "9876543210",
            "farmer_id": farmer_id,
            "farm_name": "Golden Bloom",
            "farm_location": "Nashik",
            "experience": "5 years",
            "password": password,
            "role": "ADMIN",
            "status": "VERIFIED",
        },
    )


def test_auth_authorization_and_public_regressions():
    with TestClient(app) as anonymous:
        admin = TestClient(app)
        farmer = TestClient(app)
        try:
            pending = register(anonymous, email="pending@example.com", farmer_id="FARM-101")
            assert pending.status_code == 200
            pending_body = pending.json()
            assert pending_body["status"] == "PENDING"
            assert pending_body["role"] == "FARMER"
            assert "password_hash" not in pending_body
            assert "password_salt" not in pending_body

            assert register(anonymous, email="PENDING@example.com", farmer_id="FARM-102").status_code == 409
            assert register(anonymous, email="other@example.com", farmer_id="FARM-101").status_code == 409

            pending_login = anonymous.post(
                "/api/auth/login",
                json={"email": "pending@example.com", "password": "StrongPass!123"},
            )
            assert pending_login.status_code == 403
            assert "set-cookie" not in pending_login.headers

            admin_login = admin.post(
                "/api/auth/login",
                json={"email": "admin@test.local", "password": "TestAdmin!123"},
            )
            assert admin_login.status_code == 200
            assert admin_login.json()["role"] == "ADMIN"
            admin_token = admin_login.json()["session_token"]
            assert admin_token
            assert admin.get("/api/admin/farmers?status=PENDING").json()[0]["farmer_id"] == "FARM-101"

            bearer_admin = TestClient(app)
            try:
                bearer_admin.headers.update({"Authorization": f"Bearer {admin_token}"})
                assert bearer_admin.get("/api/auth/me").status_code == 200
                assert bearer_admin.get("/api/admin/farmers?status=PENDING").status_code == 200
                assert bearer_admin.get("/api/auth/me", headers={"Authorization": "Bearer invalid-token"}).status_code == 401
                assert TestClient(app).get("/api/auth/me").status_code == 401
            finally:
                bearer_admin.close()

            assert admin.post("/api/admin/farmers/FARM-101/approve").status_code == 200
            verified_login = farmer.post(
                "/api/auth/login",
                json={"email": "pending@example.com", "password": "StrongPass!123"},
            )
            assert verified_login.status_code == 200
            farmer_token = verified_login.json()["session_token"]
            assert farmer_token
            assert farmer.get("/api/auth/me").json()["status"] == "VERIFIED"
            assert farmer.get("/api/admin/farmers").status_code == 403

            bearer_logout = TestClient(app, headers={"Authorization": f"Bearer {farmer_token}"})
            try:
                assert bearer_logout.get("/api/auth/me").status_code == 200
                assert bearer_logout.post("/api/auth/logout").status_code == 200
                assert bearer_logout.get("/api/auth/me").status_code == 401
            finally:
                bearer_logout.close()

            assert farmer.post("/api/batches", json={"batch_id": "HC-AFTER-LOGOUT"}).status_code == 401

            rejected = register(anonymous, email="rejected@example.com", farmer_id="FARM-102")
            assert rejected.status_code == 200
            assert admin.post("/api/admin/farmers/FARM-102/reject").status_code == 200
            rejected_login = anonymous.post(
                "/api/auth/login",
                json={"email": "rejected@example.com", "password": "StrongPass!123"},
            )
            assert rejected_login.status_code == 403
            assert "set-cookie" not in rejected_login.headers

            assert anonymous.post("/api/batches", json={"batch_id": "HC-UNAUTH"}).status_code == 401
            assert register(anonymous, email="pending2@example.com", farmer_id="FARM-103").status_code == 200
            pending2 = TestClient(app)
            assert pending2.post("/api/auth/login", json={"email": "pending2@example.com", "password": "StrongPass!123"}).status_code == 403
            pending2.close()

            farmer.post("/api/auth/login", json={"email": "pending@example.com", "password": "StrongPass!123"})
            created = farmer.post(
                "/api/batches",
                json={"batch_id": "HC-OWNER", "hive_id": "HIVE-001", "farmer_id": "FARM-102"},
            )
            assert created.status_code == 200
            assert created.json()["farmer_id"] == "FARM-101"

            assert farmer.post("/api/trace/HC-OWNER", json={"event_type": "processing", "description": "Packed"}).status_code == 200
            assert farmer.post("/api/batches/HC-OWNER/anchor").status_code == 200
            assert anonymous.get("/api/trace/HC-OWNER").status_code == 200
            assert anonymous.get("/api/batches/HC-OWNER").status_code == 200
            assert anonymous.get("/api/batches/HC-OWNER/qr").status_code == 200
            verification = anonymous.get("/api/verify/HC-OWNER")
            assert verification.status_code == 200
            assert verification.json()["integrity_status"] == "VALID"
            assert anonymous.get("/api/sensors/latest").status_code == 200
            assert anonymous.post("/api/sensors", json={"hive_id": "HIVE-001", "temperature": 27.1}).status_code == 200
            assert anonymous.post("/api/sensors/readings", json={"hive_id": "HIVE-001", "humidity": 54.2}).status_code == 200

            other = register(anonymous, email="other-farmer@example.com", farmer_id="FARM-104")
            assert other.status_code == 200
            assert admin.post("/api/admin/farmers/FARM-104/approve").status_code == 200
            other_client = TestClient(app)
            try:
                assert other_client.post("/api/auth/login", json={"email": "other-farmer@example.com", "password": "StrongPass!123"}).status_code == 200
                assert other_client.post("/api/admin/farmers/FARM-102/approve").status_code == 403
                assert other_client.post("/api/admin/farmers/FARM-102/reject").status_code == 403
                assert other_client.post("/api/trace/HC-OWNER", json={"event_type": "tamper", "description": "No"}).status_code == 403
                assert other_client.post("/api/batches/HC-OWNER/anchor").status_code == 403
            finally:
                other_client.close()

            with SessionLocal() as db:
                db.add(HoneyBatch(batch_id="HC-LEGACY", hive_id="HIVE-001", farmer_id=None))
                db.commit()

            assert farmer.post("/api/batches/HC-LEGACY/anchor").status_code == 403
            assert admin.post("/api/batches/HC-LEGACY/anchor").status_code == 200
            assert anonymous.get("/api/verify/HC-LEGACY").status_code == 200
        finally:
            admin.close()
            farmer.close()
