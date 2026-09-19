import hashlib
import json
from datetime import datetime
from .models import TraceEvent

def event_hash(batch_id, event_type, description, timestamp, previous_hash):
    # Stable serialization makes the SHA-256 chain independently verifiable.
    payload = json.dumps({"batch_id": batch_id, "event_type": event_type, "description": description,
                          "timestamp": timestamp.isoformat(timespec="microseconds"), "previous_hash": previous_hash or ""},
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()

def add_event(db, batch, event_type, description):
    last = db.query(TraceEvent).filter_by(batch_id=batch.batch_id).order_by(TraceEvent.id.desc()).first()
    previous_hash = last.current_hash if last else ""
    timestamp = datetime.utcnow()
    current_hash = event_hash(batch.batch_id, event_type, description, timestamp, previous_hash)
    event = TraceEvent(batch_id=batch.batch_id, event_type=event_type, description=description, timestamp=timestamp,
                       previous_hash=previous_hash, current_hash=current_hash)
    db.add(event)
    batch.previous_hash, batch.current_hash = previous_hash, current_hash
    return event

def verify(db, batch):
    previous_hash = ""
    events = db.query(TraceEvent).filter_by(batch_id=batch.batch_id).order_by(TraceEvent.id).all()
    for event in events:
        expected = event_hash(event.batch_id, event.event_type, event.description, event.timestamp, previous_hash)
        if event.previous_hash != previous_hash or event.current_hash != expected:
            return False, events
        previous_hash = event.current_hash
    return batch.current_hash == previous_hash, events
