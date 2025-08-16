from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, LargeBinary, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB  # use JSONB on Postgres

class Base(DeclarativeBase):
    pass

class File(Base):
    __tablename__ = "files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    mime: Mapped[str] = mapped_column(String(64), default="image/png")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Result(Base):
    __tablename__ = "results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    preview_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    preview_mime: Mapped[str] = mapped_column(String(32), default="image/png")
    summary: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)  # Postgres JSON
    logs: Mapped[str] = mapped_column(Text, default="")

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"), nullable=False)
    owner: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    params: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    result_id: Mapped[Optional[int]] = mapped_column(ForeignKey("results.id"), nullable=True)
