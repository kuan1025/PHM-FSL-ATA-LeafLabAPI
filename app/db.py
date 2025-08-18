import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker




DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://leaflab:leaflab@localhost:5432/leaflab"
)

# Create engine/session
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

def init_db() -> None:
    from db_models import Base
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def self_test() -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))