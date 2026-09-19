import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./honey_chain.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema():
    with engine.begin() as connection:
        try:
            connection.execute(text("ALTER TABLE trace_events ADD COLUMN IF NOT EXISTS previous_hash VARCHAR"))
        except Exception:
            pass
        try:
            connection.execute(text("ALTER TABLE trace_events ADD COLUMN IF NOT EXISTS current_hash VARCHAR"))
        except Exception:
            pass

