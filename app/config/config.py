import os
import logging
from typing import Dict, Optional, List

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from pydantic import BaseModel

LOG = logging.getLogger("leaflab.config")



# ---- AWS clients -------------------------------------------------------------
def _ssm(region: Optional[str]):
    try:
        return boto3.client("ssm", region_name=region) if region else boto3.client("ssm")
    except Exception:
        return None

def _secrets(region: Optional[str]):
    try:
        return boto3.client("secretsmanager", region_name=region) if region else boto3.client("secretsmanager")
    except Exception:
        return None

# ---- SSM fetch (per-key; no GetParametersByPath) ----------------------------
def _fetch_ssm_keys(prefix: str, region: Optional[str], keys: List[str]) -> Dict[str, str]:

    out: Dict[str, str] = {}
    cli = _ssm(region)
    if not cli or not prefix or not keys:
        return out

    fetched = 0
    for k in keys:
        name = f"{prefix.rstrip('/')}/{k}"
        try:
            r = cli.get_parameter(Name=name, WithDecryption=True)
            out[k] = r["Parameter"]["Value"]
            fetched += 1
        except ClientError:
            # Ignore not found / access denied for individual keys
            continue
        except Exception:
            continue

    LOG.info("SSM loaded %d items from %s via GetParameter(keys)", fetched, prefix)
    return out

# ---- Secrets Manager ---------------------------------------------------------
def _fetch_secret(name: str, region: Optional[str]) -> Optional[str]:
    cli = _secrets(region)
    if not cli or not name:
        return None
    try:
        r = cli.get_secret_value(SecretId=name)
        return r.get("SecretString")
    except (NoCredentialsError, BotoCoreError, ClientError) as e:
        LOG.warning("SecretsManager get_secret_value(%s) failed: %s", name, e)
        return None

# ---- Utils -------------------------------------------------------------------
def _split_csv(v: str) -> List[str]:
    return [s.strip() for s in v.split(",") if s.strip()]



# ---- Settings model ----------------------------------------------------------
class Settings(BaseModel):

    # Global const / AWS
    AWS_REGION: Optional[str] = "ap-southeast-2"
    SSM_PREFIX: Optional[str] = "/n11233885"

    # S3
    S3_BUCKET: Optional[str] = None

    # Cognito
    COGNITO_REGION: Optional[str] = None
    COGNITO_USER_POOL_ID: Optional[str] = None
    COGNITO_CLIENT_ID: Optional[str] = None
    COGNITO_CLIENT_SECRET: Optional[str] = None
    COGNITO_DOMAIN: Optional[str] = None
    COGNITO_REDIRECT_URI: Optional[str] = None
    COGNITO_LOGOUT_REDIRECT_URI: Optional[str] = None

    # CORS
    CORS_ALLOW_ORIGINS: Optional[List[str]] = None

    # Cache / Redis
    CACHE_URL: Optional[str] = None
    CACHE_S3_HEAD_TTL: Optional[int] = None
    CACHE_PRESIGN_GET_TTL: Optional[int] = None

    # SQS queues
    SQS_SAM_QUEUE_URL: Optional[str] = None
    SQS_GRABCUT_QUEUE_URL: Optional[str] = None
    SQS_SAM_DLQ_URL: Optional[str] = None
    SQS_GRABCUT_DLQ_URL: Optional[str] = None
    SQS_DISPATCH_QUEUE_URL: Optional[str] = None

    # EventBridge
    EVENT_BUS_NAME: Optional[str] = None

    # App / DB / Models
    VERSION: Optional[str] = None
    DATABASE_URL: Optional[str] = None
    PG_SCHEMA: Optional[str] = None
    PG_SSLMODE: Optional[str] = None
    SAM_MODEL_TYPE: Optional[str] = None
    SAM_CHECKPOINT: Optional[str] = None



# ---- Key groups --------------------------------------------------------------
INT_KEYS = {"CACHE_S3_HEAD_TTL", "CACHE_PRESIGN_GET_TTL"}
SECRET_KEYS = {"COGNITO_CLIENT_SECRET","DATABASE_URL"}
REQUIRED_KEYS = {"S3_BUCKET"}

# ---- Load / Merge (ENV -> SSM per-key -> Secrets) ----------------------------
def load_settings() -> Settings:
    s = Settings()
    sources: Dict[str, str] = {}

    # 1) ENV first Only for local Dev
    for field in s.model_fields:
        val = os.getenv(field)
        if val is not None and val != "":
            setattr(s, field, val)
            sources[field] = "ENV"

    # 2) SSM 
    ssm_prefix = (s.SSM_PREFIX or "").rstrip("/")
    if ssm_prefix:
        missing_for_ssm = [
            k for k in s.model_fields.keys()
            if getattr(s, k, None) in (None, "") and k not in SECRET_KEYS
        ]
        ssm_dict = _fetch_ssm_keys(ssm_prefix, s.AWS_REGION, missing_for_ssm)
        for k, v in ssm_dict.items():
            if getattr(s, k, None) in (None, "") and v not in (None, ""):
                setattr(s, k, v)
                sources[k] = "SSM"

    # 3) Secrets Manager (for sensitive keys only, still missing)
    if ssm_prefix:
        for k in SECRET_KEYS:
            if getattr(s, k, None) in (None, ""):
                sec_name = f"{ssm_prefix}/{k}"
                sec_val = _fetch_secret(sec_name, s.AWS_REGION)
                if sec_val:
                    setattr(s, k, sec_val)
                    sources[k] = "SECRETS"

    # 4) Type conversions & parsing
    for k in INT_KEYS:
        v = getattr(s, k, None)
        if v not in (None, ""):
            try:
                setattr(s, k, int(v))
            except ValueError:
                raise ValueError(f"Invalid int for {k}: {v}")

    if s.CORS_ALLOW_ORIGINS and isinstance(s.CORS_ALLOW_ORIGINS, str):
        s.CORS_ALLOW_ORIGINS = _split_csv(s.CORS_ALLOW_ORIGINS)

    # 5) debug
    missing = [k for k in REQUIRED_KEYS if getattr(s, k, None) in (None, "")]
    if missing:
        raise ValueError(f"Missing required config: {', '.join(missing)}")

    redacted = dict(sources)
    for sk in SECRET_KEYS:
        if sk in redacted:
            redacted[sk] += " (redacted)"
    LOG.info("Config sources: %s", redacted)
    LOG.info("Config ready: region=%s, ssm_prefix=%s, s3=%s, version=%s",
             s.AWS_REGION, s.SSM_PREFIX, s.S3_BUCKET, s.VERSION)

    return s
settings: Settings = load_settings()
