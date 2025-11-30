from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers.auth_cognito import router as cognito_router
from .config import settings


app = FastAPI(
    title="LeafLab Cognito Service",
    version="v1",
)

def _csv_to_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


allow_origins = _csv_to_list(settings.CORS_ALLOW_ORIGINS) or ["*"]
allow_methods = _csv_to_list(settings.CORS_ALLOW_METHODS) or ["*"]
allow_headers = _csv_to_list(settings.CORS_ALLOW_HEADERS) or ["*"]
allow_credentials = settings.CORS_ALLOW_CREDENTIALS if settings.CORS_ALLOW_CREDENTIALS is not None else False

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_credentials,
    allow_methods=allow_methods,
    allow_headers=allow_headers,
)

app.include_router(cognito_router)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
