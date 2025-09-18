from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, DateTime, Text, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import JSONB

class Base(DeclarativeBase):
    pass

# ---------- User ----------
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    cognito_sub: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    # AWS congito
    # password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    files: Mapped[list["File"]] = relationship(back_populates="owner_user")
    jobs:  Mapped[list["Job"]]  = relationship(back_populates="owner_user")

# ---------- File ----------
class File(Base):
    __tablename__ = "files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(256), default="")
    mime: Mapped[str] = mapped_column(String(64), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    s3_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    etag:   Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner_user = relationship("User", back_populates="files")

# ---------- Result ----------
class Result(Base):
    __tablename__ = "results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    preview_s3_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    preview_mime:   Mapped[str] = mapped_column(String(32), default="image/png")
    preview_size:   Mapped[int] = mapped_column(BigInteger, default=0)
    preview_etag:   Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    summary: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    logs:    Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# ---------- Job ----------
class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"), nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    params: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    created_at:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at:  Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    result_id:   Mapped[Optional[int]] = mapped_column(ForeignKey("results.id"), nullable=True)

    owner_user: Mapped["User"] = relationship(back_populates="jobs")
