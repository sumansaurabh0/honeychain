import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

DATABASE_URL=os.getenv("DATABASE_URL")

engine=create_engine(DATABASE_URL)
SessionLocal=sessionmaker(autocommit=False,autoflush=False,bind=engine)
Base=declarative_base()

def get_db():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()

def ensure_schema():
    # Compatible additions for the tamper-evident trace chain.
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE trace_events ADD COLUMN IF NOT EXISTS previous_hash VARCHAR"))
        connection.execute(text("ALTER TABLE trace_events ADD COLUMN IF NOT EXISTS current_hash VARCHAR"))
        
