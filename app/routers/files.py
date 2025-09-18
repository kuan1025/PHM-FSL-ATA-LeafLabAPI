from fastapi import APIRouter, UploadFile, File as Upload, Depends, HTTPException, Response, Query, status as http_status
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_
from typing import Optional
from datetime import datetime
import os

from db import get_db
from db_models import File as FileModel, User
from deps import current_user  
from pydantic import BaseModel, Field
from config import settings

from s3 import (
    s3_put_bytes,
    s3_head,
    s3_presign_get,
    s3_delete,
    s3_presign_put,
)

VERSION = settings.VERSION
router = APIRouter(prefix=f"/{VERSION}/files", tags=["files"])

MAX_SIZE = 100 * 1024 * 1024  # 100MB



class PresignReq(BaseModel):
    filename: str
    content_type: Optional[str] = None

class CommitReq(BaseModel):
    key: str
    filename: str

@router.post("/presign-upload", summary="Get S3 pre-signed URL (PUT) for direct client upload")
def presign_upload(req: PresignReq, user: User = Depends(current_user)):
    safe_name = os.path.basename(req.filename or "file")
    key = f"uploads/{user.id}/{int(datetime.utcnow().timestamp())}_{safe_name}"
    url = s3_presign_put(key, req.content_type or "application/octet-stream")
    return {"key": key, "url": url}


@router.post("/commit", summary="HEAD to S3 then persist metadata to DB")
def commit(req: CommitReq, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        meta = s3_head(req.key)
    except Exception as e:
        raise HTTPException(400, e)
    rec = FileModel(
        owner_id=user.id,
        filename=os.path.basename(req.filename or "file"),
        mime=meta["content_type"],
        size_bytes=meta["size"],
        s3_key=req.key,
        etag=meta["etag"],
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return {
        "id": rec.id,
        "filename": rec.filename,
        "mime": rec.mime,
        "size_bytes": rec.size_bytes,
        "s3_key": rec.s3_key,
        "etag": rec.etag,
        "created_at": rec.created_at.isoformat(),
    }


# ---------- List ----------
@router.get("/my", summary="List my files (admin sees all)")
def list_my_files(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort: str = Query("created_at:desc", description="field:order, e.g. created_at:desc"),
    q: Optional[str] = Query(None, description="Search in filename or mime (ILIKE)"),
    mime: Optional[str] = Query(None, description="Filter by exact MIME type"),
    size_min: Optional[int] = Query(None, ge=0, description="Minimum file size (bytes)"),
    size_max: Optional[int] = Query(None, ge=0, description="Maximum file size (bytes)"),
    created_from: Optional[datetime] = Query(None, description="Created at >= (ISO 8601)"),
    created_to: Optional[datetime] = Query(None, description="Created at <= (ISO 8601)"),
    owner_id: Optional[int] = Query(None, description="Admin only: filter by owner_id"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    response: Response = None,
):
    conds = []
    print("debug : " ,user.role)
    if user.role != "admin":
        if owner_id is not None:
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Permission denied: admin role required")
        conds.append(FileModel.owner_id == user.id)
    else:
        if owner_id is not None:
            conds.append(FileModel.owner_id == owner_id)

    if q:
        conds.append(or_(FileModel.filename.ilike(f"%{q}%"), FileModel.mime.ilike(f"%{q}%")))
    if mime:
        conds.append(FileModel.mime == mime)
    if size_min is not None:
        conds.append(FileModel.size_bytes >= size_min)
    if size_max is not None:
        conds.append(FileModel.size_bytes <= size_max)
    if created_from is not None:
        conds.append(FileModel.created_at >= created_from)
    if created_to is not None:
        conds.append(FileModel.created_at <= created_to)

    allowed_sort = {
        "created_at": FileModel.created_at,
        "id": FileModel.id,
        "filename": FileModel.filename,
        "size_bytes": FileModel.size_bytes,
    }
    try:
        field, order = (sort.split(":") + ["asc"])[:2]
    except Exception:
        field, order = "created_at", "desc"
    col = allowed_sort.get(field, FileModel.created_at)
    order_by = col.desc() if str(order).lower() == "desc" else col.asc()

    count_stmt = select(func.count()).select_from(FileModel)
    if conds:
        count_stmt = count_stmt.where(*conds)
    total = db.scalar(count_stmt)

    offset = (page - 1) * page_size
    list_stmt = (select(FileModel).where(*conds) if conds else select(FileModel))
    list_stmt = list_stmt.order_by(order_by).offset(offset).limit(page_size)
    rows = db.execute(list_stmt).scalars().all()

    items = [
        {
            "id": r.id,
            "filename": r.filename or "",
            "mime": r.mime,
            "size_bytes": r.size_bytes or 0,
            "created_at": r.created_at.isoformat(),
            "owner_id": r.owner_id,
            "s3_key": r.s3_key,
            "etag": r.etag
        }
        for r in rows
    ]

    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
        "sort": f"{field}:{order}",
        "filters": {
            "q": q, "mime": mime, "size_min": size_min, "size_max": size_max,
            "created_from": created_from.isoformat() if created_from else None,
            "created_to": created_to.isoformat() if created_to else None,
            "owner_id": owner_id if user.role == "admin" else None,
        },
    }


# ---------- download ----------
@router.get("/{file_id}", summary="Get presigned download URL")
def get_download_url(
    file_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rec = db.get(FileModel, file_id)
    if not rec:
        raise HTTPException(status_code=404, detail="file not found")
    if user.role != "admin" and rec.owner_id != user.id:
        raise HTTPException(status_code=403, detail="permission denied")
    return {"url": s3_presign_get(rec.s3_key), "mime": rec.mime, "size_bytes": rec.size_bytes, "etag": rec.etag}


# ---------- Delete（DB + S3） ----------
@router.delete("/{file_id}", status_code=200, summary="Delete my file (S3 + DB)")
def delete_image(
    file_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rec = db.get(FileModel, file_id)
    if not rec:
        raise HTTPException(status_code=404, detail="file not found")
    if user.role != "admin" and rec.owner_id != user.id:
        raise HTTPException(status_code=403, detail="permission denied")
    try:
        s3_delete(rec.s3_key)
    finally:
        db.delete(rec)
        db.commit()
    return {"message": "file deleted successfully", "id": file_id, "deleted_at": datetime.utcnow().isoformat()}


# ---------- Update） ----------
class FileUpdate(BaseModel):
    filename: Optional[str] = Field(None, min_length=1, max_length=256, description="New filename (no path)")

@router.put("/{file_id}/content", summary="Replace file content (and optionally rename) on S3")
async def replace_file_content(
    file_id: int,
    f: UploadFile = Upload(...),
    filename: Optional[str] = Query(None, description="Override stored filename"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    rec = db.get(FileModel, file_id)
    if not rec:
        raise HTTPException(status_code=404, detail="file not found")
    if user.role != "admin" and rec.owner_id != user.id:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="permission denied")

    data = await f.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=413, detail=f"file too large (> {MAX_SIZE} bytes)")

    content_type = f.content_type or rec.mime or "application/octet-stream"
    s3_put_bytes(rec.s3_key, data, content_type)
    meta = s3_head(rec.s3_key)

    rec.size_bytes = meta["size"]
    rec.mime = meta["content_type"]
    rec.etag = meta["etag"]


    new_name = None
    if filename is not None:
        new_name = os.path.basename(filename).strip()
    elif f.filename:
        new_name = os.path.basename(f.filename).strip()
    if new_name:
        if len(new_name) > 256:
            raise HTTPException(status_code=400, detail="filename too long")
        rec.filename = new_name

    db.commit()
    db.refresh(rec)
    return {
        "id": rec.id,
        "filename": rec.filename,
        "mime": rec.mime,
        "size_bytes": rec.size_bytes,
        "created_at": rec.created_at.isoformat(),
        "owner_id": rec.owner_id,
        "etag": rec.etag,
        "download_url": s3_presign_get(rec.s3_key),
        "message": "file content updated successfully",
    }
