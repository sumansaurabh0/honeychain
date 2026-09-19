from datetime import datetime
from .ledger import verify

def public_batch(db, batch):
    valid, events = verify(db, batch)
    return {"batch_id": batch.batch_id, "hive_id": batch.hive_id, "harvest_date": batch.harvest_date,
            "weight": batch.weight, "status": batch.status, "traceability": events,
            "ledger_integrity": valid, "verification_timestamp": datetime.utcnow(),
            "verification_url": f"/verify/{batch.batch_id}"}
