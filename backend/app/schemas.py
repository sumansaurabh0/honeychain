from pydantic import BaseModel, Field

class HiveCreate(BaseModel):
    hive_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=200)

class SensorCreate(BaseModel):
    # Keep compatible with the fixed ESP32/simulator payload.
    hive_id: str = Field(min_length=1, max_length=100)
    temperature: float = Field(ge=-40, le=85)
    humidity: float = Field(ge=0, le=100)
    weight: float = Field(ge=0, le=1000)
    gas_raw: float = Field(ge=0, le=4095)
    mic_raw: float = Field(ge=0, le=4095)

class BatchCreate(BaseModel):
    batch_id: str = Field(min_length=1, max_length=100)
    hive_id: str = Field(min_length=1, max_length=100)
    harvest_date: str = Field(min_length=1, max_length=30)
    weight: float = Field(gt=0, le=1000)

class TraceCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=2000)
