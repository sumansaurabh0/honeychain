from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine,Base,ensure_schema
from .routes import router
from . import models

Base.metadata.create_all(bind=engine)
ensure_schema()

app=FastAPI(title="Honey Chain API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173","http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)

@app.get("/")
def root():
    return {"project":"Honey Chain","status":"running"}

@app.get("/db-test")
def db_test():
    try:
        with engine.connect():
            return {"database":"connected"}
    except Exception:
        return {"database":"error"}
