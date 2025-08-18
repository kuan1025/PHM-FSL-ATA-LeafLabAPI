# app/models.py
from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, LargeBinary, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB  

class Base(DeclarativeBase):
    pass

# User
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user")  # "user" | "admin"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    files: Mapped[list["File"]] = relationship(back_populates="owner_user")
    jobs: Mapped[list["Job"]] = relationship(back_populates="owner_user")

class File(Base):
    __tablename__ = "files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(256), default="")
    mime: Mapped[str] = mapped_column(String(64), default="image/png")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner_user = relationship("User")

class Result(Base):
    __tablename__ = "results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    preview_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    preview_mime: Mapped[str] = mapped_column(String(32), default="image/png")
    summary: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False) 
    logs: Mapped[str] = mapped_column(Text, default="")

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"), nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    params: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    result_id: Mapped[Optional[int]] = mapped_column(ForeignKey("results.id"), nullable=True)

    owner_user: Mapped["User"] = relationship(back_populates="jobs")
