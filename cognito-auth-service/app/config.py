import os
from functools import lru_cache
from typing import Dict, List, Optional

from pydantic import BaseModel


class Settings(BaseModel):
    COGNITO_REGION: Optional[str] = None
    COGNITO_USER_POOL_ID: Optional[str] = None
    COGNITO_CLIENT_ID: Optional[str] = None
    COGNITO_CLIENT_SECRET: Optional[str] = None
    COGNITO_DOMAIN: Optional[str] = None
    COGNITO_REDIRECT_URI: Optional[str] = None
    COGNITO_LOGOUT_REDIRECT_URI: Optional[str] = None
    COOKIE_DOMAIN: Optional[str] = None
    CORS_ALLOW_ORIGINS: Optional[str] = None
    CORS_ALLOW_METHODS: Optional[str] = None
    CORS_ALLOW_HEADERS: Optional[str] = None
    CORS_ALLOW_CREDENTIALS: Optional[bool] = None


REQUIRED_KEYS: List[str] = [
    "COGNITO_REGION",
    "COGNITO_USER_POOL_ID",
    "COGNITO_CLIENT_ID",
    "COGNITO_DOMAIN",
    "COGNITO_REDIRECT_URI",
]


def _load_env() -> Dict[str, Optional[str]]:
    return {field: os.getenv(field) for field in Settings.model_fields.keys()}


def _validate(settings: Settings) -> None:
    missing = [
        key for key in REQUIRED_KEYS
        if getattr(settings, key, None) in (None, "")
    ]
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(f"Missing required configuration values: {missing_str}")


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    data = _load_env()
    settings = Settings(**data)
    _validate(settings)
    return settings


settings = load_settings()
