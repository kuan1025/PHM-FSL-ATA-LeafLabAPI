from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

Base = declarative_base()

class File(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True)
    owner = Column(String, nullable=False)
    orig_name = Column(String, nullable=False)
    path = Column(String, nullable=False)
    mime = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Result(Base):
    __tablename__ = "results"
    id = Column(Integer, primary_key=True)
    summary = Column(JSONB, default={})
    preview_path = Column(String, nullable=True)
    logs = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    owner = Column(String, nullable=False)
    status = Column(String, default="queued")  # queued|running|done|error
    params = Column(JSONB, default={})
    meta = Column(JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    result_id = Column(Integer, ForeignKey("results.id"), nullable=True)
    file = relationship("File")
    result = relationship("Result", uselist=False)
