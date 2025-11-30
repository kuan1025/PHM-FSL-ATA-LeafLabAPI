import os, logging
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from config.db import init_db
from routers.files import router as files_router
from routers.jobs import router as jobs_router
from routers.auth_cognito import router as cognito_router
from routers.dlq import router as dlq_router
from config.config import settings



def setup_logging():
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"

    logging.basicConfig(level=logging.INFO, format=fmt)

    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)

    cache_logger = logging.getLogger("leaflab.cache")
    cache_logger.setLevel(logging.INFO)


    if not cache_logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(fmt))
        cache_logger.addHandler(h)
        cache_logger.propagate = False

setup_logging()


app = FastAPI(
    title="LeafLab API",
    version="v1",
    root_path="/api",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# CORS
origins = settings.CORS_ALLOW_ORIGINS
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


app.include_router(files_router)
app.include_router(jobs_router)
# Move to cognito-auth-service
# app.include_router(cognito_router)
app.include_router(dlq_router)


@app.get("/")
def index():
    return {"ok": True, "docs": "/docs"}

@app.get("/health")
def health():
    if os.getenv("FAIL_HEALTH") == "1":
        return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return {"status": "ok"}


