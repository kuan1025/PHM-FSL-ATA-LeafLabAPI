import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import init_db, SessionLocal
from auth import router as auth_router
from routers.files import router as files_router
from routers.jobs import router as jobs_router


from db_models import User  
from security import hash_password 

app = FastAPI(title="LeafLab API", version="v1")


origins = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

@app.on_event("startup")
def _startup():
    
    init_db()

    db = SessionLocal()
    try:
        def upsert(username: str, role: str, raw_pwd: str = "password"):
            u = db.query(User).filter(User.username == username).first()
            if u is None:
                db.add(User(username=username, role=role, password_hash=hash_password(raw_pwd)))
            else:
                u.role = role
                u.password_hash = hash_password(raw_pwd)
            db.commit()

        upsert("admin", "admin")
        upsert("kuan", "user")
    finally:
        db.close()


app.include_router(auth_router, prefix="/api")
app.include_router(files_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")


@app.get("/")
def index():
    return {"ok": True, "docs": "/docs"}
