from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .database import get_db
from .health import assess
from .ledger import add_event, verify
from .models import Hive, SensorReading, HoneyBatch, TraceEvent
from .schemas import HiveCreate, SensorCreate, BatchCreate, TraceCreate
from .verification import public_batch

router = APIRouter(prefix="/api")

def missing(kind):
    raise HTTPException(status_code=404, detail=f"{kind} not found")

def hive(db, hive_id):
    return db.query(Hive).filter_by(hive_id=hive_id).first() or missing("Hive")

def batch(db, batch_id):
    return db.query(HoneyBatch).filter_by(batch_id=batch_id).first() or missing("Batch")

@router.post("/hives", status_code=status.HTTP_201_CREATED)
def create_hive(data: HiveCreate, db: Session = Depends(get_db)):
    if db.query(Hive.id).filter_by(hive_id=data.hive_id).first():
        raise HTTPException(status_code=409, detail="Hive already exists")
    item = Hive(**data.model_dump())
    db.add(item); db.commit(); db.refresh(item)
    return item

@router.get("/hives")
def get_hives(db: Session = Depends(get_db)):
    return db.query(Hive).all()

@router.post("/sensors", status_code=status.HTTP_201_CREATED)
def add_sensor(data: SensorCreate, db: Session = Depends(get_db)):
    hive(db, data.hive_id)
    item = SensorReading(**data.model_dump())
    db.add(item); db.commit(); db.refresh(item)
    return item

@router.get("/sensors/{hive_id}")
def get_sensors(hive_id: str, db: Session = Depends(get_db)):
    hive(db, hive_id)
    return db.query(SensorReading).filter_by(hive_id=hive_id).order_by(SensorReading.id.desc()).limit(50).all()

@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    latest = db.query(SensorReading).order_by(SensorReading.id.desc()).first()
    return {"hive_count": db.query(Hive).count(), "active_hive_count": db.query(Hive).filter_by(status="active").count(),
            "batch_count": db.query(HoneyBatch).count(), "latest_sensor": latest}

@router.get("/health/{hive_id}")
def health(hive_id: str, db: Session = Depends(get_db)):
    hive(db, hive_id)
    reading = db.query(SensorReading).filter_by(hive_id=hive_id).order_by(SensorReading.id.desc()).first()
    if not reading: missing("Sensor reading")
    return {"hive_id": hive_id, "timestamp": reading.timestamp, **assess(reading)}

def create_batch_item(data, db):
    hive(db, data.hive_id)
    if db.query(HoneyBatch.id).filter_by(batch_id=data.batch_id).first():
        raise HTTPException(status_code=409, detail="Batch already exists")
    item = HoneyBatch(**data.model_dump())
    db.add(item); db.flush()
    add_event(db, item, "harvest", "Honey batch created from harvest")
    db.commit(); db.refresh(item)
    return item

@router.post("/batches", status_code=status.HTTP_201_CREATED)
def create_batch(data: BatchCreate, db: Session = Depends(get_db)):
    return create_batch_item(data, db)

@router.post("/harvests", status_code=status.HTTP_201_CREATED)
def create_harvest(data: BatchCreate, db: Session = Depends(get_db)):
    return create_batch_item(data, db)

@router.get("/batches/{batch_id}")
def get_batch(batch_id: str, db: Session = Depends(get_db)):
    return batch(db, batch_id)

@router.post("/trace/{batch_id}", status_code=status.HTTP_201_CREATED)
def create_trace(batch_id: str, data: TraceCreate, db: Session = Depends(get_db)):
    item = batch(db, batch_id)
    event = add_event(db, item, data.event_type, data.description)
    db.commit(); db.refresh(event)
    return event

@router.get("/trace/{batch_id}")
def get_trace(batch_id: str, db: Session = Depends(get_db)):
    batch(db, batch_id)
    return db.query(TraceEvent).filter_by(batch_id=batch_id).order_by(TraceEvent.id).all()

@router.get("/ledger/{batch_id}")
def ledger_status(batch_id: str, db: Session = Depends(get_db)):
    item = batch(db, batch_id)
    valid, events = verify(db, item)
    return {"batch_id": batch_id, "ledger_integrity": valid, "event_count": len(events), "current_hash": item.current_hash}

@router.get("/verify/{batch_id}")
def verify_batch(batch_id: str, db: Session = Depends(get_db)):
    return public_batch(db, batch(db, batch_id))

@router.get("/batches/{batch_id}/qr")
def qr_url(batch_id: str, db: Session = Depends(get_db)):
    batch(db, batch_id)
    # Public frontend route used by QR scanners.
    return {"batch_id": batch_id, "verification_url": f"/verify/{batch_id}"}
