import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from db import init_db
from auth import router as auth_router
from routers.files import router as files_router
from routers.jobs import router as jobs_router
from routers.admin import router as admin_router
from fastapi.middleware.cors import CORSMiddleware



app = FastAPI(title="LeafLab API", version="v1")

# cross -> frontend
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

app.include_router(auth_router)
app.include_router(files_router)
app.include_router(jobs_router)
app.include_router(admin_router)

@app.get("/")
def index():
    return {"ok": True, "docs": "/docs"}
