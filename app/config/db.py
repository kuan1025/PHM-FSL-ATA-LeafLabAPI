import os
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.url import make_url

from config.db_models import Base
from config.config import settings


DATABASE_URL = settings.DATABASE_URL

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")
url = make_url(DATABASE_URL)

# Locol dev
PG_SCHEMA = settings.PG_SCHEMA                   
USE_SSL = settings.PG_SSLMODE



connect_args = {}
if USE_SSL:
    connect_args["sslmode"] = "require"

connect_args.update({
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 5,
})

engine = create_engine(
    url,
    pool_pre_ping=True,    
    pool_recycle=300,     
    pool_size=5,
    max_overflow=10,
    connect_args=connect_args,
    future=True,
)


@event.listens_for(engine, "connect")
def _set_search_path(dbapi_conn, conn_record):
    if PG_SCHEMA:
        cur = dbapi_conn.cursor()
        try:
            cur.execute(f'SET search_path TO "{PG_SCHEMA}"')
        finally:
            cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                            expire_on_commit=False, future=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        db.close()

def init_db():

    if PG_SCHEMA:
        try:
            with engine.begin() as conn:
                conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{PG_SCHEMA}"'))
        except Exception:
            pass


    with engine.begin() as conn:
        Base.metadata.create_all(bind=conn)

        jobs_table = f'"{PG_SCHEMA}".jobs' if PG_SCHEMA else 'jobs'
        conn.execute(text(f"ALTER TABLE {jobs_table} ADD COLUMN IF NOT EXISTS failure_count INTEGER NOT NULL DEFAULT 0"))
        conn.execute(text(f"ALTER TABLE {jobs_table} ADD COLUMN IF NOT EXISTS failure_reason TEXT"))


def self_test() -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
