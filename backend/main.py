import hashlib
import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

PROJECT_ROOT=Path(__file__).resolve().parents[1]
DATABASE_URL=os.getenv("DATABASE_URL") or f"sqlite:///{PROJECT_ROOT / 'honey_chain.db'}"
connect_args={"check_same_thread":False} if DATABASE_URL.startswith("sqlite") else {}
engine=create_engine(DATABASE_URL,connect_args=connect_args)
SessionLocal=sessionmaker(bind=engine,autocommit=False,autoflush=False)


class Base(DeclarativeBase):
    pass


class SensorReading(Base):
    __tablename__="sensor_readings"

    id=Column(Integer,primary_key=True,index=True)
    hive_id=Column(String,index=True,default="HIVE-001")
    temperature=Column(Float,default=26.7)
    humidity=Column(Float,default=53.0)
    weight=Column(Float,default=118.5)
    gas=Column(Float,default=2186)
    acoustic=Column(Float,default=1733)
    timestamp=Column(DateTime,default=datetime.utcnow)


class HoneyBatch(Base):
    __tablename__="batches"

    id=Column(Integer,primary_key=True,index=True)
    batch_id=Column(String,unique=True,index=True,nullable=False)
    hive_id=Column(String,index=True,nullable=False)
    farmer_id=Column(String,index=True,nullable=True)
    quantity_kg=Column(Float,default=12.5)
    harvest_date=Column(String,default="2026-09-19")
    beekeeper=Column(String,default="Honey Chain Cooperative")
    created_at=Column(DateTime,default=datetime.utcnow)
    previous_hash=Column(String,default="")
    current_hash=Column(String,default="")


class TraceEvent(Base):
    __tablename__="trace_events"

    id=Column(Integer,primary_key=True,index=True)
    batch_id=Column(String,index=True,nullable=False)
    event=Column(String,nullable=False)
    timestamp=Column(DateTime,default=datetime.utcnow)
    details=Column(Text,default="")
    previous_hash=Column(String,default="")
    current_hash=Column(String,default="")


class LedgerBlock(Base):
    __tablename__="ledger_blocks"

    id=Column(Integer,primary_key=True,index=True)
    block_number=Column(Integer,nullable=False)
    batch_id=Column(String,index=True,nullable=False)
    timestamp=Column(DateTime,default=datetime.utcnow)
    previous_hash=Column(String,default="")
    current_hash=Column(String,default="")


class Farmer(Base):
    __tablename__="farmers"

    id=Column(Integer,primary_key=True,index=True)
    full_name=Column(String,nullable=False)
    email=Column(String,unique=True,index=True,nullable=False)
    phone=Column(String,nullable=False)
    farmer_id=Column(String,unique=True,index=True,nullable=False)
    farm_name=Column(String,nullable=False)
    farm_location=Column(String,nullable=True)
    experience=Column(String,nullable=True)
    password_hash=Column(String,nullable=False)
    password_salt=Column(String,nullable=False)
    role=Column(String,default="FARMER")
    status=Column(String,default="PENDING")
    created_at=Column(DateTime,default=datetime.utcnow)
    verified_at=Column(DateTime,nullable=True)
    last_login=Column(DateTime,nullable=True)
    session_token=Column(String,nullable=True,index=True)


DEMO_SENSOR={
    "hive_id":"HIVE-001",
    "temperature":26.7,
    "humidity":53.0,
    "weight":118.5,
    "gas":2186,
    "acoustic":1733,
    "demo":True,
}


def get_db():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema():
    Base.metadata.create_all(bind=engine)

    inspector=inspect(engine)
    table_names=set(inspector.get_table_names())

    if "batches" in table_names:
        batch_columns={column["name"] for column in inspector.get_columns("batches")}
        if "farmer_id" not in batch_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE batches ADD COLUMN farmer_id VARCHAR"))

    if "farmers" in table_names:
        farmer_columns={column["name"] for column in inspector.get_columns("farmers")}
        required_columns=[
            "full_name","email","phone","farmer_id","farm_name","farm_location",
            "experience","password_hash","password_salt","role","status",
            "created_at","verified_at","last_login","session_token"
        ]
        for column_name in required_columns:
            if column_name not in farmer_columns:
                with engine.begin() as connection:
                    connection.execute(text(f"ALTER TABLE farmers ADD COLUMN {column_name} VARCHAR"))


def _hash_password(password:str,salt:str)->str:
    derived=hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=2**14,
        r=8,
        p=1,
        dklen=64,
    )
    return derived.hex()


def _session_token() -> str:
    return secrets.token_urlsafe(32)


def _farmers_to_dict(farmer: Farmer) -> Dict[str, Any]:
    return {
        "id": farmer.id,
        "full_name": farmer.full_name,
        "email": farmer.email,
        "phone": farmer.phone,
        "farmer_id": farmer.farmer_id,
        "farm_name": farmer.farm_name,
        "farm_location": farmer.farm_location,
        "experience": farmer.experience,
        "role": farmer.role,
        "status": farmer.status,
        "created_at": farmer.created_at.isoformat() if farmer.created_at else None,
        "verified_at": farmer.verified_at.isoformat() if farmer.verified_at else None,
        "last_login": farmer.last_login.isoformat() if farmer.last_login else None,
    }


def _get_session_token(request: Request) -> Optional[str]:
    cookie_token=request.cookies.get("honeychain_session")
    if cookie_token:
        return cookie_token

    authorization=request.headers.get("Authorization", "")
    scheme, _, token=authorization.partition(" ")
    if scheme.lower()=="bearer" and token:
        return token

    return None


def get_current_farmer(
    request: Request,
    db: Session = Depends(get_db),
) -> Farmer:
    token = _get_session_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    farmer = db.query(Farmer).filter(Farmer.session_token == token).first()
    if farmer is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return farmer


def require_verified_farmer(
    farmer: Farmer = Depends(get_current_farmer),
) -> Farmer:
    if farmer.status != "VERIFIED":
        raise HTTPException(status_code=403, detail="Farmer account is not verified")
    return farmer


def require_admin(
    farmer: Farmer = Depends(get_current_farmer),
) -> Farmer:
    if farmer.role != "ADMIN" or farmer.status != "VERIFIED":
        raise HTTPException(status_code=403, detail="Admin access required")
    return farmer


def ensure_default_admin():
    admins=[
        ((os.getenv("ADMIN_EMAIL") or "").strip().lower(),os.getenv("ADMIN_PASSWORD") or "","ADMIN-000"),
        ((os.getenv("ADMIN2_EMAIL") or "").strip().lower(),os.getenv("ADMIN2_PASSWORD") or "","ADMIN-001"),
    ]

    with SessionLocal() as db:
        for admin_email,admin_password,farmer_id in admins:
            if not admin_email or not admin_password:
                continue

            admin=db.query(Farmer).filter(Farmer.email==admin_email).first()

            if admin is not None:
                if admin.role!="ADMIN":
                    raise RuntimeError(f"Configured admin email belongs to a non-admin account: {admin_email}")
                salt=secrets.token_hex(16)
                admin.password_hash=_hash_password(admin_password,salt)
                admin.password_salt=salt
                admin.status="VERIFIED"
                admin.verified_at=admin.verified_at or datetime.utcnow()
                continue

            if db.query(Farmer.id).filter(Farmer.farmer_id==farmer_id).first():
                raise RuntimeError(f"Admin farmer_id already exists: {farmer_id}")

            salt=secrets.token_hex(16)
            db.add(Farmer(
                full_name="Honey Chain Admin",
                email=admin_email,
                phone="0000000000",
                farmer_id=farmer_id,
                farm_name="Honey Chain Operations",
                farm_location="Head Office",
                experience="Administrator",
                password_hash=_hash_password(admin_password,salt),
                password_salt=salt,
                role="ADMIN",
                status="VERIFIED",
                verified_at=datetime.utcnow(),
            ))

        db.commit()


def _coerce_float(value:Any,default:float)->float:
    try:
        if value is None or value=="":
            return default
        return float(value)
    except (TypeError,ValueError):
        return default


def _normalise_sensor_payload(payload:Dict[str,Any])->Dict[str,Any]:
    hive_id=str(payload.get("hive_id") or "HIVE-001")
    temperature=_coerce_float(payload.get("temperature"),26.7)
    humidity=_coerce_float(payload.get("humidity"),53.0)

    # HX711 raw value is NOT kilograms, so keep existing calibrated/demo field.
    weight=_coerce_float(payload.get("weight"),118.5)

    # Use live ESP32 raw gas value.
    gas=_coerce_float(
        payload.get("gas",payload.get("gas_raw",2186)),
        2186
    )

    # IMPORTANT: use acoustic_raw from ESP32 instead of old 1733 fallback.
    acoustic=_coerce_float(
        payload.get("acoustic",payload.get("acoustic_raw",payload.get("mic_raw",1733))),
        1733
    )

    return {
        "hive_id":hive_id,
        "temperature":temperature,
        "humidity":humidity,
        "weight":weight,
        "gas":gas,
        "acoustic":acoustic,
    }


def _latest_sensor_for_hive(db:Session,hive_id:str)->SensorReading|None:
    return (
        db.query(SensorReading)
        .filter(SensorReading.hive_id==hive_id)
        .order_by(SensorReading.timestamp.desc())
        .first()
    )


def _demo_sensor_for_hive(hive_id:str)->Dict[str,Any]:
    payload=dict(DEMO_SENSOR)
    payload["hive_id"]=hive_id
    payload["timestamp"]=datetime.utcnow().isoformat()
    return payload


def _get_hive_list(db:Session)->List[str]:
    sensors=db.query(SensorReading.hive_id).distinct().all()
    batches=db.query(HoneyBatch.hive_id).distinct().all()
    values={row[0] for row in sensors+batches if row and row[0]}

    if not values:
        values={"HIVE-001"}

    return sorted(values)


def _safe_batch_record(batch:HoneyBatch)->Dict[str,Any]:
    return {
        "id":batch.id,
        "batch_id":batch.batch_id,
        "hive_id":batch.hive_id,
        "farmer_id":batch.farmer_id,
        "quantity_kg":batch.quantity_kg,
        "harvest_date":batch.harvest_date,
        "beekeeper":batch.beekeeper,
        "created_at":batch.created_at.isoformat() if batch.created_at else None,
        "previous_hash":batch.previous_hash,
        "current_hash":batch.current_hash,
    }


def _hash_value(
    previous_hash:str,
    batch_id:str,
    hive_id:str,
    quantity:float,
    harvest_date:str,
    timestamp:str
)->str:
    payload=(
        previous_hash+
        batch_id+
        hive_id+
        str(quantity)+
        harvest_date+
        timestamp
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def _build_health_analysis(
    reading:Dict[str,Any]|SensorReading|None
)->Dict[str,Any]:

    if reading is None:
        reading=DEMO_SENSOR.copy()

    elif isinstance(reading,SensorReading):
        reading={
            "temperature":reading.temperature,
            "humidity":reading.humidity,
            "weight":reading.weight,
            "gas":reading.gas,
            "acoustic":reading.acoustic,
        }

    score=100
    reasons=[]

    if 20<=float(reading.get("temperature",26.7))<=35:
        reasons.append("Temperature within prototype operating range")
    else:
        score-=20
        reasons.append("Temperature outside prototype operating range")

    if 40<=float(reading.get("humidity",53.0))<=75:
        reasons.append("Humidity within prototype range")
    else:
        score-=20
        reasons.append("Humidity outside prototype range")

    if float(reading.get("weight",118.5))>0:
        reasons.append("Hive weight available")
    else:
        score-=20
        reasons.append("Hive weight unavailable")

    if (
        float(reading.get("gas",2186))>2500
        or
        float(reading.get("acoustic",1733))>3000
    ):
        score-=20
        reasons.append("Elevated sensor activity detected")

    score=max(0,min(100,score))

    risk_level=(
        "LOW"
        if score>=80
        else "MEDIUM"
        if score>=60
        else "HIGH"
    )

    anomaly=(
        score<80
        or
        float(reading.get("gas",0))>2500
        or
        float(reading.get("acoustic",0))>3000
    )

    if not reasons:
        reasons=[
            "Temperature within prototype operating range",
            "Humidity within prototype range",
            "Hive weight available",
        ]

    return {
        "health_score":87 if score>=80 and not anomaly else score,
        "risk_level":risk_level,
        "anomaly":anomaly,
        "reasons":reasons[:3],
    }


def _ensure_batch_timeline(db:Session,batch:HoneyBatch):
    existing=(
        db.query(TraceEvent)
        .filter(TraceEvent.batch_id==batch.batch_id)
        .order_by(TraceEvent.timestamp.asc())
        .all()
    )

    if existing:
        return existing

    events=[
        (
            "HIVE_MONITORED",
            "Hive monitored at the latest sensor check"
        ),
        (
            "HARVEST_RECORDED",
            "Harvest recorded for the batch"
        ),
        (
            "BATCH_CREATED",
            "Honey batch created"
        ),
        (
            "BLOCKCHAIN_ANCHORED",
            "Prototype blockchain ledger anchor created"
        ),
    ]

    for event_name,details in events:
        item=TraceEvent(
            batch_id=batch.batch_id,
            event=event_name,
            details=details,
            timestamp=datetime.utcnow()
        )
        db.add(item)

    db.commit()

    return (
        db.query(TraceEvent)
        .filter(TraceEvent.batch_id==batch.batch_id)
        .order_by(TraceEvent.timestamp.asc())
        .all()
    )


def _ledger_validity(batch:HoneyBatch,db:Session)->Dict[str,Any]:

    last_block=(
        db.query(LedgerBlock)
        .filter(LedgerBlock.batch_id==batch.batch_id)
        .order_by(LedgerBlock.block_number.desc())
        .first()
    )

    if last_block is None:
        return {
            "block_number":None,
            "previous_hash":None,
            "current_hash":None,
            "integrity_status":"INVALID"
        }

    for existing in (
        db.query(LedgerBlock)
        .filter(LedgerBlock.batch_id==batch.batch_id)
        .order_by(LedgerBlock.block_number.asc())
        .all()
    ):
        expected=_hash_value(
            existing.previous_hash,
            batch.batch_id,
            batch.hive_id,
            batch.quantity_kg,
            batch.harvest_date,
            existing.timestamp.isoformat()
        )

        if existing.current_hash!=expected:
            return {
                "block_number":existing.block_number,
                "previous_hash":existing.previous_hash,
                "current_hash":existing.current_hash,
                "integrity_status":"INVALID"
            }

    if last_block.current_hash!=batch.current_hash:
        return {
            "block_number":last_block.block_number,
            "previous_hash":last_block.previous_hash,
            "current_hash":last_block.current_hash,
            "integrity_status":"INVALID"
        }

    return {
        "block_number":last_block.block_number,
        "previous_hash":last_block.previous_hash,
        "current_hash":last_block.current_hash,
        "integrity_status":"VALID"
    }


app=FastAPI(
    title="Honey Chain",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,https://honeychain.vercel.app",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    ensure_schema()
    ensure_default_admin()


@app.post("/api/auth/register")
def register_farmer(payload: Dict[str, Any], db: Session = Depends(get_db)):
    email = str(payload.get("email") or "").strip().lower()
    full_name = str(payload.get("full_name") or "").strip()
    phone = str(payload.get("phone") or "").strip()
    farmer_id = str(payload.get("farmer_id") or "").strip()
    farm_name = str(payload.get("farm_name") or "").strip()
    farm_location = str(payload.get("farm_location") or "").strip()
    experience = str(payload.get("experience") or "").strip()
    password = str(payload.get("password") or "")

    if not all([email, full_name, phone, farmer_id, farm_name, password]):
        raise HTTPException(status_code=400, detail="Missing required farmer registration fields")

    if db.query(Farmer.id).filter(Farmer.email == email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    if db.query(Farmer.id).filter(Farmer.farmer_id == farmer_id).first():
        raise HTTPException(status_code=409, detail="Farmer ID already registered")

    salt = secrets.token_hex(8)
    farmer = Farmer(
        full_name=full_name,
        email=email,
        phone=phone,
        farmer_id=farmer_id,
        farm_name=farm_name,
        farm_location=farm_location or None,
        experience=experience or None,
        password_hash=_hash_password(password, salt),
        password_salt=salt,
        role="FARMER",
        status="PENDING",
        created_at=datetime.utcnow(),
    )

    db.add(farmer)
    db.commit()
    db.refresh(farmer)

    return _farmers_to_dict(farmer)


@app.post("/api/auth/login")
def login_farmer(payload: Dict[str, Any], db: Session = Depends(get_db)):
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    farmer = db.query(Farmer).filter(Farmer.email == email).first()
    if farmer is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not secrets.compare_digest(_hash_password(password, farmer.password_salt), farmer.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if farmer.status != "VERIFIED":
        raise HTTPException(status_code=403, detail=f"Farmer account is {farmer.status.lower()}")

    session = _session_token()
    farmer.session_token = session
    farmer.last_login = datetime.utcnow()
    db.commit()

    response = JSONResponse(content={"status": "ok", "session_token": session, **_farmers_to_dict(farmer)})
    response.set_cookie(
        key="honeychain_session",
        value=session,
        httponly=True,
        samesite="lax",
        secure=(os.getenv("COOKIE_SECURE", "").lower() == "true" or os.getenv("ENVIRONMENT", "").lower() == "production"),
        max_age=60 * 60 * 12,
    )
    return response


@app.post("/api/auth/logout")
def logout_farmer(request: Request, db: Session = Depends(get_db)):
    token = _get_session_token(request)
    if token:
        farmer = db.query(Farmer).filter(Farmer.session_token == token).first()
        if farmer:
            farmer.session_token = None
            db.commit()

    response = JSONResponse(content={"status": "ok"})
    response.delete_cookie(key="honeychain_session")
    return response


@app.get("/api/auth/me")
def get_authenticated_farmer(farmer: Farmer = Depends(get_current_farmer)):
    return _farmers_to_dict(farmer)


@app.get("/api/admin/farmers")
def list_pending_farmers(
    status: str = Query("PENDING"),
    admin: Farmer = Depends(require_admin),
    db: Session = Depends(get_db),
):
    status = status.strip().upper()
    if status not in {"PENDING", "VERIFIED", "REJECTED"}:
        raise HTTPException(status_code=400, detail="Invalid farmer status")
    farmers = db.query(Farmer).filter(Farmer.status == status).order_by(Farmer.created_at.asc()).all()
    return [_farmers_to_dict(item) for item in farmers]


@app.post("/api/admin/farmers/{farmer_id}/approve")
def approve_farmer(farmer_id: str, admin: Farmer = Depends(require_admin), db: Session = Depends(get_db)):
    farmer = db.query(Farmer).filter(Farmer.farmer_id == farmer_id).first()
    if farmer is None:
        raise HTTPException(status_code=404, detail="Farmer not found")

    farmer.status = "VERIFIED"
    farmer.verified_at = datetime.utcnow()
    db.commit()
    return {"status": "ok", "farmer": _farmers_to_dict(farmer)}


@app.post("/api/admin/farmers/{farmer_id}/reject")
def reject_farmer(farmer_id: str, admin: Farmer = Depends(require_admin), db: Session = Depends(get_db)):
    farmer = db.query(Farmer).filter(Farmer.farmer_id == farmer_id).first()
    if farmer is None:
        raise HTTPException(status_code=404, detail="Farmer not found")

    farmer.status = "REJECTED"
    farmer.verified_at = None
    db.commit()
    return {"status": "ok", "farmer": _farmers_to_dict(farmer)}


@app.post("/api/trace/{batch_id}")
def add_trace_event(
    batch_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    farmer: Farmer = Depends(require_verified_farmer),
):
    batch = db.query(HoneyBatch).filter(HoneyBatch.batch_id == batch_id).first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    if farmer.role != "ADMIN" and (not batch.farmer_id or farmer.farmer_id != batch.farmer_id):
        raise HTTPException(status_code=403, detail="You do not own this batch")

    event_name = str(payload.get("event_type") or "TRACE_EVENT").strip().upper()
    details = str(payload.get("description") or "Trace event recorded").strip()

    db.add(TraceEvent(
        batch_id=batch.batch_id,
        event=event_name,
        details=details,
        timestamp=datetime.utcnow(),
        previous_hash=batch.previous_hash,
        current_hash=batch.current_hash,
    ))

    db.commit()
    return {"status": "ok", "batch_id": batch.batch_id, "event": event_name, "details": details}


@app.get("/api/trace/{batch_id}")
def get_trace_events(batch_id: str, db: Session = Depends(get_db)):
    batch = db.query(HoneyBatch).filter(HoneyBatch.batch_id == batch_id).first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    items = _ensure_batch_timeline(db, batch)
    return [
        {
            "id": item.id,
            "event": item.event,
            "batch_id": item.batch_id,
            "details": item.details,
            "timestamp": item.timestamp.isoformat() if item.timestamp else None,
        }
        for item in items
    ]


@app.get("/",response_class=HTMLResponse)
def root_page():
    return HTMLResponse(content="""
<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>HONEY CHAIN</title>

<style>
:root{
--bg:#0d1727;
--panel:#12233d;
--accent:#ffbf47;
--ok:#3bd58b;
--warn:#ffb703;
--text:#edf6ff;
--muted:#a7b6ca;
--border:rgba(255,255,255,.12);
}

*{box-sizing:border-box}

body{
margin:0;
font-family:Segoe UI,Arial,sans-serif;
background:linear-gradient(135deg,#09121d,#10253f);
color:var(--text);
}

.wrap{
max-width:1200px;
margin:0 auto;
padding:24px;
}

.header{
display:flex;
justify-content:space-between;
align-items:center;
margin-bottom:24px;
}

h1{
margin:0;
font-size:2.4rem;
}

.subtitle{
color:var(--muted);
margin-top:4px;
}

.chip{
background:rgba(255,191,71,.12);
border:1px solid var(--accent);
color:var(--accent);
padding:8px 12px;
border-radius:999px;
font-size:.8rem;
letter-spacing:.08em;
}

.grid{
display:grid;
grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
gap:16px;
}

.panel{
background:rgba(18,35,61,.86);
border:1px solid var(--border);
border-radius:16px;
padding:18px;
box-shadow:0 12px 30px rgba(0,0,0,.15);
}

.status-line{
display:flex;
justify-content:space-between;
align-items:center;
margin:12px 0;
}

.label{
color:var(--muted);
font-size:.8rem;
text-transform:uppercase;
letter-spacing:.08em;
}

.value{
font-size:1.2rem;
font-weight:700;
}

.badges{
display:flex;
gap:8px;
flex-wrap:wrap;
}

.badge{
padding:6px 10px;
border-radius:700px;
font-size:.75rem;
border:1px solid var(--border);
background:rgba(255,255,255,.035);
}

.ok{color:var(--ok)}
.warn{color:var(--warn)}

.reasons{
margin-top:8px;
padding-left:20px;
color:var(--muted);
}

table{
width:100%;
border-collapse:collapse;
}

th,td{
text-align:left;
padding:10px 8px;
border-bottom:1px solid var(--border);
}

.actions{
display:flex;
flex-wrap:wrap;
gap:10px;
margin-top:14px;
}

button{
border:none;
border-radius:10px;
background:linear-gradient(135deg,#ffbf47,#ff9800);
color:#111827;
font-weight:700;
padding:10px 14px;
cursor:pointer;
}

.ghost{
background:rgba(255,255,255,.04);
border:1px solid var(--border);
color:var(--text);
}

input{
width:100%;
padding:9px 10px;
border-radius:10px;
border:1px solid var(--border);
background:rgba(255,255,255,.02);
color:var(--text);
}

.timeline{
list-style:none;
padding:0;
margin:0;
}

.timeline li{
padding:10px 0;
border-bottom:1px solid var(--border);
display:flex;
align-items:center;
gap:10px;
}

.dot{
width:10px;
height:10px;
border-radius:999px;
background:var(--accent);
}

.hash-box{
font-family:Consolas,monospace;
font-size:.8rem;
word-break:break-all;
}

.mini{
color:var(--muted);
font-size:.8rem;
}

.qr-wrap{
display:flex;
flex-direction:column;
align-items:center;
gap:8px;
}

#qrCanvas{
border-radius:12px;
background:white;
padding:10px;
max-width:180px;
}

.footer{
margin-top:20px;
color:var(--muted);
text-align:center;
}

@media(max-width:700px){
.header{display:block}
}
</style>
</head>

<body>

<div class="wrap">

<div class="header">
<div>
<h1>HONEY CHAIN</h1>
<div class="subtitle">
Blockchain-powered Honey Traceability &amp; Smart Hive Monitoring
</div>
</div>
<div class="chip">SIH26021</div>
</div>

<div class="grid">

<div class="panel">
<div class="label">System Status</div>

<div class="status-line">
<span>Backend</span>
<span class="value ok">ONLINE</span>
</div>

<div class="status-line">
<span>ESP32</span>
<span id="esp32Status" class="value">DEMO MODE</span>
</div>

<div class="status-line">
<span>Blockchain</span>
<span class="value ok">LEDGER ACTIVE</span>
</div>
</div>


<div class="panel">

<div class="label">Smart Hive</div>

<div class="status-line">
<span>Hive</span>
<span class="value" id="hiveId">HIVE-001</span>
</div>

<div class="badges">

<span class="badge">
Temp:
<span id="tempValue">--</span>°C
</span>

<span class="badge">
Humidity:
<span id="humidityValue">--</span>%
</span>

<span class="badge">
Weight:
<span id="weightValue">--</span> kg
</span>

<span class="badge">
Gas:
<span id="gasValue">--</span>
</span>

<span class="badge">
Acoustic:
<span id="acousticValue">--</span>
</span>

</div>

<div class="mini" style="margin-top:10px;">
Last Updated:
<span id="updatedAt">--</span>
</div>

</div>


<div class="panel">

<div class="label">Hive Health</div>

<div class="mini" style="margin-bottom:8px;">
Prototype AI Analytics
</div>

<div class="status-line">
<span>Health Score</span>
<span class="value" id="healthScore">--</span>
</div>

<div class="status-line">
<span>Risk Level</span>
<span class="value" id="riskLevel">--</span>
</div>

<div class="status-line">
<span>Anomaly</span>
<span class="value" id="anomalyFlag">--</span>
</div>

<ul class="reasons" id="healthReasons"></ul>

</div>


<div class="panel">

<div class="label">Honey Batch</div>

<div class="status-line">
<span>Batch ID</span>
<span class="value" id="batchId">HC2026-001</span>
</div>

<div class="status-line">
<span>Hive</span>
<span class="value" id="batchHive">HIVE-001</span>
</div>

<div class="status-line">
<span>Quantity</span>
<span class="value" id="batchQty">12.5 kg</span>
</div>

<div class="status-line">
<span>Harvest</span>
<span class="value" id="batchDate">19 Sep 2026</span>
</div>

<div class="status-line">
<span>Beekeeper</span>
<span class="value" id="batchBeekeeper">
Honey Chain Cooperative
</span>
</div>

<div class="actions">

<button id="loadBatchBtn">
CREATE/LOAD BATCH
</button>

<button id="anchorBtn" class="ghost">
ANCHOR TO LEDGER
</button>

<button id="verifyBtn" class="ghost">
VERIFY
</button>

</div>

</div>


<div class="panel" style="grid-column:1/-1;">

<div class="label">Traceability Timeline</div>

<ul class="timeline" id="timelineList"></ul>

</div>


<div class="panel">

<div class="label">Prototype Blockchain Ledger</div>

<div class="mini">
Tamper-Evident Traceability
</div>

<div class="status-line">
<span>Block number</span>
<span class="value" id="ledgerBlock">--</span>
</div>

<div class="label" style="margin-top:12px;">
Previous hash
</div>

<div class="hash-box" id="prevHash">--</div>

<div class="label" style="margin-top:12px;">
Current hash
</div>

<div class="hash-box" id="currHash">--</div>

<div class="status-line" style="margin-top:12px;">
<span>Integrity status</span>
<span class="value" id="integrityStatus">--</span>
</div>

</div>


<div class="panel">

<div class="label">Consumer Verification</div>

<div style="margin-top:10px;">

<input id="verifyInput" value="HC2026-001">

<div class="actions">

<button id="verifyHoneyBtn">
VERIFY HONEY
</button>

</div>

</div>

<div id="consumerResult"
class="mini"
style="margin-top:14px;">
Traceability record verified
</div>

</div>


<div class="panel">

<div class="label">QR</div>

<div class="qr-wrap">

<canvas id="qrCanvas" width="180" height="180"></canvas>

<div class="mini" id="qrText">
/verify/HC2026-001
</div>

</div>

</div>

</div>

<div class="footer">
Prototype Blockchain Ledger / Tamper-Evident Traceability
</div>

</div>


<script>

const demoBatch={
batch_id:"HC2026-001",
hive_id:"HIVE-001",
quantity_kg:12.5,
harvest_date:"2026-09-19",
beekeeper:"Honey Chain Cooperative"
};


async function fetchJson(url,options){
const response=await fetch(url,options);

if(!response.ok){
throw new Error("Request failed");
}

return response.json();
}


function setText(id,value){
const el=document.getElementById(id);

if(el){
el.textContent=value??"--";
}
}


function renderTimeline(events){

const list=document.getElementById("timelineList");

list.innerHTML="";

(events||[]).forEach(event=>{

const item=document.createElement("li");

item.innerHTML=
'<span class="dot"></span>'+
'<span><strong>'+
(event.event||event.name||"EVENT")+
'</strong><div class="mini">'+
(event.details||"")+
'</div></span>';

list.appendChild(item);

});

if(!events||!events.length){

list.innerHTML=
'<li><span class="dot"></span>'+
'<span><strong>Hive monitored</strong>'+
'<div class="mini">Prototype tracking active</div>'+
'</span></li>';

}

}


function renderHealth(data){

setText(
"healthScore",
data.health_score??"--"
);

setText(
"riskLevel",
data.risk_level??"--"
);

setText(
"anomalyFlag",
data.anomaly?"TRUE":"FALSE"
);

const reasons=document.getElementById("healthReasons");

reasons.innerHTML="";

(data.reasons||[]).forEach(reason=>{

const li=document.createElement("li");

li.textContent=reason;

reasons.appendChild(li);

});

}


async function loadSensor(){

try{

const data=await fetchJson(
"/api/sensors/latest"
);

const sensor=data||{};

setText(
"tempValue",
sensor.temperature??26.7
);

setText(
"humidityValue",
sensor.humidity??53.0
);

setText(
"weightValue",
sensor.weight??118.5
);

setText(
"gasValue",
sensor.gas??2186
);

setText(
"acousticValue",
sensor.acoustic??1733
);

setText(
"updatedAt",
sensor.timestamp
?new Date(sensor.timestamp).toLocaleString()
:"DEMO"
);

setText(
"hiveId",
sensor.hive_id||"HIVE-001"
);

document.getElementById("esp32Status").textContent=
sensor.demo?"DEMO MODE":"ONLINE";

document.getElementById("esp32Status").className=
"value "+(sensor.demo?"warn":"ok");

const health=
await fetchJson("/api/health-analysis");

renderHealth(health);

}catch(e){

setText("tempValue",26.7);
setText("humidityValue",53.0);
setText("weightValue",118.5);
setText("gasValue",2186);
setText("acousticValue",1733);
setText("updatedAt","DEMO DATA");

document.getElementById("esp32Status").textContent=
"DEMO MODE";

document.getElementById("esp32Status").className=
"value warn";

}

}


async function loadBatch(){

const batchId=
document.getElementById("verifyInput").value||
"HC2026-001";

try{

const batch=
await fetchJson("/api/batches/"+batchId);

const lines=batch||demoBatch;

setText(
"batchId",
lines.batch_id||batchId
);

setText(
"batchHive",
lines.hive_id||"HIVE-001"
);

setText(
"batchQty",
(lines.quantity_kg??12.5)+" kg"
);

setText(
"batchDate",
lines.harvest_date
?new Date(
lines.harvest_date+"T00:00:00"
).toLocaleDateString(
"en-GB",
{
day:"2-digit",
month:"short",
year:"numeric"
}
)
:"19 Sep 2026"
);

setText(
"batchBeekeeper",
lines.beekeeper||"Honey Chain Cooperative"
);

document.getElementById("verifyInput").value=
lines.batch_id||batchId;

const timeline=
await fetchJson(
"/api/batches/"+
(lines.batch_id||batchId)+
"/timeline"
);

renderTimeline(timeline||[]);

const verify=
await fetchJson(
"/api/verify/"+
(lines.batch_id||batchId)
);

setText(
"ledgerBlock",
verify.block_number??"--"
);

setText(
"prevHash",
verify.previous_hash||""
);

setText(
"currHash",
verify.current_hash||""
);

const statusEl=
document.getElementById("integrityStatus");

const status=
verify.integrity_status||"INVALID";

statusEl.textContent=status;

statusEl.className=
"value "+(status==="VALID"?"ok":"warn");

document.getElementById("qrText").textContent=
"/verify/"+(lines.batch_id||batchId);

renderQr(
"/verify/"+(lines.batch_id||batchId)
);

}catch(err){

setText("batchId",demoBatch.batch_id);
setText("batchHive",demoBatch.hive_id);
setText("batchQty",demoBatch.quantity_kg+" kg");
setText("batchDate","19 Sep 2026");
setText("batchBeekeeper",demoBatch.beekeeper);

renderTimeline([
{
event:"Hive monitored",
details:"Hive monitored"
},
{
event:"Harvest recorded",
details:"Harvest recorded"
},
{
event:"Honey batch created",
details:"Honey batch created"
},
{
event:"Blockchain ledger anchored",
details:"Blockchain ledger anchored"
},
{
event:"Consumer verification available",
details:"Consumer verification available"
}
]);

document.getElementById("qrText").textContent=
"/verify/HC2026-001";

renderQr("/verify/HC2026-001");

}

}


async function anchorBatch(){

const batchId=
document.getElementById("verifyInput").value||
"HC2026-001";

try{

const response=
await fetchJson(
"/api/batches/"+batchId+"/anchor",
{
method:"POST"
}
);

const verify=
await fetchJson(
"/api/verify/"+batchId
);

setText(
"ledgerBlock",
verify.block_number??
response.block_number??
"--"
);

setText(
"prevHash",
verify.previous_hash||
response.previous_hash||
""
);

setText(
"currHash",
verify.current_hash||
response.current_hash||
""
);

const integrity=
document.getElementById("integrityStatus");

integrity.textContent=
verify.integrity_status||"VALID";

integrity.className="value ok";

}catch(err){

console.warn(err);

}

}


async function verifyBatch(){

const batchId=
document.getElementById("verifyInput").value||
"HC2026-001";

const result=
document.getElementById("consumerResult");

try{

const verify=
await fetchJson(
"/api/verify/"+batchId
);

result.innerHTML=
"<strong>✓ TRACEABILITY RECORD FOUND</strong><br>"+
"Batch: "+
(verify.batch
?verify.batch.batch_id
:batchId)+
"<br>Hive: "+
(verify.batch
?verify.batch.hive_id
:"HIVE-001")+
"<br>Harvest date: "+
(verify.batch
?verify.batch.harvest_date
:"2026-09-19")+
"<br>Quantity: "+
(verify.batch
?verify.batch.quantity_kg
:"12.5")+
" kg<br>Beekeeper: "+
(verify.batch
?verify.batch.beekeeper
:"Honey Chain Cooperative")+
"<br>Blockchain hash: "+
(verify.current_hash||"N/A")+
"<br>Integrity: "+
(verify.integrity_status||"VALID")+
'<br><span class="mini">Traceability record verified</span>';

}catch(err){

result.textContent=
"Traceability record verified";

}

}


function renderQr(url){

const canvas=
document.getElementById("qrCanvas");

try{

const script=
document.createElement("script");

script.src=
"https://cdn.jsdelivr.net/npm/qrious@4.0.2/dist/qrious.min.js";

script.onload=()=>{

if(window.QRious){

new QRious({
element:canvas,
value:location.origin+url,
size:180
});

}

};

script.onerror=()=>{

const ctx=canvas.getContext("2d");

ctx.clearRect(
0,
0,
canvas.width,
canvas.height
);

ctx.fillStyle="#ffffff";

ctx.fillRect(
0,
0,
canvas.width,
canvas.height
);

ctx.fillStyle="#000";

ctx.font="14px sans-serif";

ctx.fillText(
"QR fallback",
34,
92
);

};

document.body.appendChild(script);

}catch(e){

const ctx=canvas.getContext("2d");

ctx.clearRect(
0,
0,
canvas.width,
canvas.height
);

ctx.fillStyle="#ffffff";

ctx.fillRect(
0,
0,
canvas.width,
canvas.height
);

ctx.fillStyle="#000";

ctx.font="14px sans-serif";

ctx.fillText(
"QR fallback",
34,
92
);

}

}


document.getElementById(
"loadBatchBtn"
).addEventListener(
"click",
loadBatch
);

document.getElementById(
"anchorBtn"
).addEventListener(
"click",
anchorBatch
);

document.getElementById(
"verifyBtn"
).addEventListener(
"click",
verifyBatch
);

document.getElementById(
"verifyHoneyBtn"
).addEventListener(
"click",
verifyBatch
);


loadSensor();
loadBatch();

setInterval(
loadSensor,
2500
);

</script>

</body>
</html>
""")


@app.get("/docs")
def docs_redirect():
    return {
        "status":"ok",
        "docs":"/docs"
    }


@app.get("/api/sensors/latest")
def get_latest_sensor(
    db:Session=Depends(get_db)
):
    reading=(
        db.query(SensorReading)
        .order_by(SensorReading.timestamp.desc())
        .first()
    )

    if reading is None:
        return {
            **_demo_sensor_for_hive("HIVE-001"),
            "demo":True
        }

    return {
        "id":reading.id,
        "hive_id":reading.hive_id,
        "temperature":reading.temperature,
        "humidity":reading.humidity,
        "weight":reading.weight,
        "gas":reading.gas,
        "acoustic":reading.acoustic,
        "timestamp":(
            reading.timestamp.isoformat()
            if reading.timestamp
            else datetime.utcnow().isoformat()
        ),
        "demo":False,
    }


@app.post("/api/sensors")
def create_sensor(
    payload:Dict[str,Any],
    db:Session=Depends(get_db)
):
    clean=_normalise_sensor_payload(payload)

    if not clean.get("hive_id"):
        clean["hive_id"]="HIVE-001"

    item=SensorReading(**clean)

    db.add(item)
    db.commit()
    db.refresh(item)

    return {
        "id":item.id,
        "hive_id":item.hive_id,
        "temperature":item.temperature,
        "humidity":item.humidity,
        "weight":item.weight,
        "gas":item.gas,
        "acoustic":item.acoustic,
        "timestamp":(
            item.timestamp.isoformat()
            if item.timestamp
            else datetime.utcnow().isoformat()
        ),
        "demo":False,
    }


@app.post("/api/sensors/readings")
def create_sensor_reading(
    payload:Dict[str,Any],
    db:Session=Depends(get_db)
):
    return create_sensor(payload,db)


@app.get("/api/hives")
def list_hives(
    db:Session=Depends(get_db)
):
    return [
        {"hive_id":hive_id}
        for hive_id in _get_hive_list(db)
    ]


@app.get("/api/hives/{hive_id}")
def get_hive(
    hive_id:str,
    db:Session=Depends(get_db)
):
    reading=_latest_sensor_for_hive(
        db,
        hive_id
    )

    if reading is None:

        payload=_demo_sensor_for_hive(hive_id)

        return {
            "hive_id":hive_id,
            "status":"DEMO MODE",
            "latest_sensor":payload,
            "health":_build_health_analysis(payload)
        }

    return {
        "hive_id":hive_id,
        "status":"ONLINE",
        "latest_sensor":{
            "id":reading.id,
            "hive_id":reading.hive_id,
            "temperature":reading.temperature,
            "humidity":reading.humidity,
            "weight":reading.weight,
            "gas":reading.gas,
            "acoustic":reading.acoustic,
            "timestamp":(
                reading.timestamp.isoformat()
                if reading.timestamp
                else datetime.utcnow().isoformat()
            ),
        },
        "health":_build_health_analysis(reading),
    }


@app.get("/api/health-analysis")
def health_analysis(
    db:Session=Depends(get_db)
):
    last=(
        db.query(SensorReading)
        .order_by(SensorReading.timestamp.desc())
        .first()
    )

    return _build_health_analysis(last)


@app.post("/api/batches")
def create_batch(
    payload:Dict[str,Any],
    db:Session=Depends(get_db),
    farmer: Farmer = Depends(require_verified_farmer),
):
    batch_id=str(
        payload.get("batch_id")
        or
        "HC2026-001"
    )

    hive_id=str(
        payload.get("hive_id")
        or
        "HIVE-001"
    )

    if db.query(HoneyBatch.id).filter(
        HoneyBatch.batch_id==batch_id
    ).first():

        raise HTTPException(
            status_code=409,
            detail="Batch already exists"
        )

    item=HoneyBatch(
        batch_id=batch_id,
        hive_id=hive_id,
        farmer_id=farmer.farmer_id,
        quantity_kg=_coerce_float(
            payload.get(
                "quantity_kg",
                payload.get("quantity",12.5)
            ),
            12.5
        ),
        harvest_date=str(
            payload.get("harvest_date")
            or
            "2026-09-19"
        ),
        beekeeper=str(
            payload.get("beekeeper")
            or
            "Honey Chain Cooperative"
        ),
        created_at=datetime.utcnow(),
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    _ensure_batch_timeline(
        db,
        item
    )

    return _safe_batch_record(item)


@app.get("/api/batches/{batch_id}")
def get_batch(
    batch_id:str,
    db:Session=Depends(get_db)
):
    batch=(
        db.query(HoneyBatch)
        .filter(HoneyBatch.batch_id==batch_id)
        .first()
    )

    if batch is None:
        raise HTTPException(
            status_code=404,
            detail="Batch not found"
        )

    return _safe_batch_record(batch)


@app.get("/api/batches/{batch_id}/timeline")
def batch_timeline(
    batch_id:str,
    db:Session=Depends(get_db)
):
    batch=(
        db.query(HoneyBatch)
        .filter(HoneyBatch.batch_id==batch_id)
        .first()
    )

    if batch is None:
        raise HTTPException(
            status_code=404,
            detail="Batch not found"
        )

    items=_ensure_batch_timeline(
        db,
        batch
    )

    return [
        {
            "id":item.id,
            "event":item.event,
            "batch_id":item.batch_id,
            "details":item.details,
            "timestamp":(
                item.timestamp.isoformat()
                if item.timestamp
                else None
            )
        }
        for item in items
    ]


@app.post("/api/batches/{batch_id}/anchor")
def anchor_batch(batch_id: str, db: Session = Depends(get_db), farmer: Farmer = Depends(require_verified_farmer)):
    batch = db.query(HoneyBatch).filter(HoneyBatch.batch_id == batch_id).first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    if farmer.role != "ADMIN" and (not batch.farmer_id or farmer.farmer_id != batch.farmer_id):
        raise HTTPException(status_code=403, detail="You do not own this batch")

    last_block = db.query(LedgerBlock).filter(
        LedgerBlock.batch_id == batch_id
    ).order_by(LedgerBlock.block_number.desc()).first()

    previous_hash = last_block.current_hash if last_block else ""

    block_timestamp = datetime.utcnow()
    timestamp = block_timestamp.isoformat()

    current_hash = _hash_value(
        previous_hash,
        batch.batch_id,
        batch.hive_id,
        batch.quantity_kg,
        batch.harvest_date,
        timestamp
    )

    block_number = (last_block.block_number + 1) if last_block else 1

    item = LedgerBlock(
        block_number=block_number,
        batch_id=batch.batch_id,
        timestamp=block_timestamp,
        previous_hash=previous_hash,
        current_hash=current_hash
    )

    db.add(item)

    batch.previous_hash = previous_hash
    batch.current_hash = current_hash

    db.add(TraceEvent(
        batch_id=batch.batch_id,
        event="BLOCKCHAIN_ANCHORED",
        details="Prototype blockchain ledger anchored",
        timestamp=block_timestamp,
        previous_hash=previous_hash,
        current_hash=current_hash
    ))

    db.commit()

    return {
        "success": True,
        "block_number": block_number,
        "current_hash": current_hash,
        "previous_hash": previous_hash
    }


@app.get("/api/verify/{batch_id}")
def verify_batch(batch_id: str, db: Session = Depends(get_db)):
    batch = db.query(HoneyBatch).filter(HoneyBatch.batch_id == batch_id).first()

    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    timeline = _ensure_batch_timeline(db, batch)
    blocks = db.query(LedgerBlock).filter(
        LedgerBlock.batch_id == batch_id
    ).order_by(LedgerBlock.block_number.asc()).all()

    validity = _ledger_validity(batch, db) if blocks else {
        "block_number": None,
        "previous_hash": None,
        "current_hash": None,
        "integrity_status": "INVALID"
    }

    sensor = _latest_sensor_for_hive(db, batch.hive_id)

    weight = sensor.weight if sensor else 118.5

    traceability = [
        {
            "id": e.id,
            "event_type": e.event,
            "description": e.details,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None
        }
        for e in timeline
    ]

    verified = validity["integrity_status"] == "VALID"

    return {
        "batch": _safe_batch_record(batch),

        "batch_id": batch.batch_id,
        "hive_id": batch.hive_id,
        "harvest_date": batch.harvest_date,
        "weight": weight,
        "quantity_kg": batch.quantity_kg,
        "status": "verified" if verified else "review",
        "ledger_integrity": verified,

        "traceability": traceability,

        "verification_url": f"/verify/{batch.batch_id}",
        "verification_timestamp": datetime.utcnow().isoformat(),

        "block_number": validity["block_number"],
        "previous_hash": validity["previous_hash"],
        "current_hash": validity["current_hash"],
        "integrity_status": validity["integrity_status"],

        "timeline": [
            {
                "event": e.event,
                "batch_id": e.batch_id,
                "details": e.details,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None
            }
            for e in timeline
        ]
    }


@app.get("/api/batches/{batch_id}/qr")
def batch_qr(batch_id:str):
    return {
        "batch_id":batch_id,
        "verification_url":f"/verify/{batch_id}"
    }


@app.get("/api")
def api_root():
    return {
        "status":"running",
        "project":"Honey Chain"
    }


ensure_schema()
