import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .db import init_db
from .auth import router as auth_router
from .routers.files import router as files_router
from .routers.jobs import router as jobs_router
from .routers.weather import router as weather_router
from .routers.admin import router as admin_router
from .routers.leaf import router as leaf_router




app = FastAPI(title="LeafLab API", version="v1")
init_db()
app.include_router(auth_router)
app.include_router(files_router)
app.include_router(jobs_router)
app.include_router(weather_router)
app.include_router(admin_router)
app.include_router(leaf_router)

@app.get("/")
def index():
    return {"ok": True, "docs": "/docs"}
