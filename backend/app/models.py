from sqlalchemy import Column,Integer,String,Float,DateTime,Text
from datetime import datetime
from .database import Base

class Hive(Base):
    __tablename__="hives"
    id=Column(Integer,primary_key=True)
    hive_id=Column(String,unique=True,index=True)
    name=Column(String)
    location=Column(String)
    status=Column(String,default="active")

class SensorReading(Base):
    __tablename__="sensor_readings"
    id=Column(Integer,primary_key=True)
    hive_id=Column(String,index=True)
    temperature=Column(Float)
    humidity=Column(Float)
    weight=Column(Float)
    gas_raw=Column(Float)
    mic_raw=Column(Float)
    timestamp=Column(DateTime,default=datetime.utcnow)

class HoneyBatch(Base):
    __tablename__="honey_batches"
    id=Column(Integer,primary_key=True)
    batch_id=Column(String,unique=True,index=True)
    hive_id=Column(String)
    harvest_date=Column(String)
    weight=Column(Float)
    status=Column(String,default="verified")
    current_hash=Column(String)
    previous_hash=Column(String)

class TraceEvent(Base):
    __tablename__="trace_events"
    id=Column(Integer,primary_key=True)
    batch_id=Column(String,index=True)
    event_type=Column(String)
    description=Column(Text)
    timestamp=Column(DateTime,default=datetime.utcnow)
    previous_hash=Column(String)
    current_hash=Column(String)
