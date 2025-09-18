from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi import status as http_status, Response
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from datetime import datetime
from typing import Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError
import os

from db import get_db ,SessionLocal
from db_models import Job, Result, File, User
from deps import current_user  
from processing import heavy_pipeline, decode_image_from_bytes, encode_png
from s3 import s3_get_bytes, s3_put_bytes, s3_head, s3_presign_get

VERSION = os.environ.get("VERSION", "v1")
router = APIRouter(prefix=f"/{VERSION}/jobs", tags=["jobs"])

MethodT  = Literal["sam", "grabcut"]
WBModeT  = Literal["none", "grayworld"]
StatusT  = Literal["queued", "running", "done", "error"]


class CreateJobOptions(BaseModel):
    method: MethodT = Field("sam", description="Segmentation backend: 'sam' or 'grabcut'.")
    white_balance: WBModeT = Field("none", description="WB for GrabCut only.")
    gamma: float = Field(1.0, description="Gamma for GrabCut only.")
    repeat: int = Field(8, ge=1, le=64, description="Repeat count to increase CPU load.")


CREATE_JOB_EXAMPLES = {
    "SAM": {"summary": "SAM (no preprocessing)", "value": {"method": "sam", "repeat": 8}},
    "SAM_with_Preproc": {"summary": "SAM + preprocessing (ignored by SAM)", "value": {"method": "sam", "white_balance": "grayworld", "gamma": 1.12, "repeat": 8}},
    "GrabCut": {"summary": "GrabCut (no preprocessing)", "value": {"method": "grabcut", "white_balance": "none", "gamma": 1.0, "repeat": 8}},
    "GrabCut_with_Preproc": {"summary": "GrabCut + preprocessing", "value": {"method": "grabcut", "white_balance": "grayworld", "gamma": 1.12, "repeat": 8}},
}

# ---------- helpers ----------
def _is_admin(user: User) -> bool:
    return getattr(user, "role", "user") == "admin"

def _require_admin(user: User):
    if not _is_admin(user):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Permission denied: admin role required")

def _ensure_owner_or_admin(user: User, owner_id: int, *, resource: str = "job"):
    if _is_admin(user):
        return
    if user.id != owner_id:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail=f"Permission denied: not the {resource} owner")


# -----------------------------
# Create (single) — file_id as query input
# -----------------------------
@router.post(
    "", status_code=201,
    summary="Create a job (segment)",
    description="`file_id` is a query parameter. Options are provided in the JSON body.",
)
def create_job(
    file_id: int = Query(..., description="ID of the file to process"),
    body: CreateJobOptions = Body(..., openapi_examples=CREATE_JOB_EXAMPLES),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    f = db.get(File, file_id)  
    if not f:
        raise HTTPException(404, "file not found")
    if not _is_admin(user) and f.owner_id != user.id:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Permission denied: not the file owner")

    job = Job(file_id=file_id, owner_id=user.id, params=body.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"id": job.id, "status": job.status, "params": job.params, "owner_id": job.owner_id}


# -----------------------------
# Start (single, synchronous)
# -----------------------------
@router.post(
    "/{job_id}/start",
    summary="Start a job (single, synchronous)",
    description="Executes the job immediately and returns the result id (if successful).",
)
def start_job(job_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")

    _ensure_owner_or_admin(user, job.owner_id, resource="job")

    if job.status not in ("queued", "error"):
        return {"status": job.status, "result_id": job.result_id}

    owner_id = int(user.id)
    jid = int(job.id)
    file_id = int(job.file_id)

    job.status = "running"
    job.started_at = datetime.utcnow()
    db.commit()

    try:
        db.close()
    except Exception:
        pass


    with SessionLocal() as s_read:
        file_rec = s_read.get(File, file_id)
        if not file_rec or not file_rec.s3_key:
            with SessionLocal() as s_err:
                jb = s_err.get(Job, jid)
                if jb:
                    jb.status = "error"
                    jb.finished_at = datetime.utcnow()
                    s_err.commit()
            raise HTTPException(500, "file content missing (s3_key)")
        s3_key = str(file_rec.s3_key)

    try:
        # 2) run pipeline
        img_bytes = s3_get_bytes(s3_key)
        img = decode_image_from_bytes(img_bytes)

        with SessionLocal() as s_params:
            j = s_params.get(Job, jid)
            if not j:
                raise RuntimeError("job vanished")
            params: Dict[str, Any] = j.params or {}

        method: MethodT = params.get("method", "sam")
        wb: WBModeT = params.get("white_balance", "none")
        gamma: float = float(params.get("gamma", 1.0))
        repeat: int = int(params.get("repeat", 8))
        if method == "sam":
            wb, gamma = "none", 1.0
        feats, preview, logs = heavy_pipeline(
            img_bgr=img, repeat=repeat, white_balance=wb, gamma=gamma, method=method
        )

        preview_bytes = encode_png(preview)
        preview_key = f"results/{user.id}/{job.id}/preview.png"
        s3_put_bytes(preview_key, preview_bytes, "image/png")
        meta = s3_head(preview_key)

    except Exception as e:
        with SessionLocal() as s_err:
            jb = s_err.get(Job, jid)
            if jb:
                jb.status = "error"
                jb.finished_at = datetime.utcnow()
                s_err.commit()
        raise HTTPException(500, f"processing failed: {e}")

    # -------------------------
    # (C) rewrite
    # -------------------------
    def _write_back():
        with SessionLocal() as s_w:
            # 1)  results
            res = Result(
                summary=feats,
                preview_s3_key=preview_key,
                preview_mime="image/png",
                preview_size=meta["size"],
                preview_etag=meta["etag"],
                logs=logs,
            )
            s_w.add(res)
            s_w.commit()
            s_w.refresh(res)

            # 2)  job
            jb = s_w.get(Job, jid)
            if not jb:
                raise RuntimeError("job vanished before finalize")
            jb.result_id = res.id
            jb.status = "done"
            jb.finished_at = datetime.utcnow()
            s_w.commit()
            return res.id

    try:
        result_id = _write_back()
    except OperationalError:
        result_id = _write_back()
    except Exception as e:
        with SessionLocal() as s_err:
            jb = s_err.get(Job, jid)
            if jb:
                jb.status = "error"
                jb.finished_at = datetime.utcnow()
                s_err.commit()
        raise HTTPException(500, f"db write failed: {e}")

    return {"status": "done", "result_id": result_id}


# -----------------------------
# Admin: requeue
# -----------------------------
@router.put("/{job_id}/requeue", summary="Admin requeue a job")
def requeue_job(job_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    job.status = "queued"
    job.started_at = None
    job.finished_at = None
    job.result_id = None
    db.commit()
    return {"id": job.id, "status": job.status}


# -----------------------------
# List / Get / Preview / Delete
# -----------------------------
@router.get("", summary="List jobs (admin sees all)")
def list_jobs(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    sort: str = Query("created_at:desc", description="field:order, e.g. created_at:desc"),
    status: Optional[StatusT] = Query(None, description="Filter by job status"),
    owner_id: Optional[int]   = Query(None, description="Admin only: filter by owner_id"),
    file_id: Optional[int]    = Query(None, description="Filter by file_id"),
    has_result: Optional[bool]= Query(None, description="Filter by presence of result"),
    created_from: Optional[datetime] = Query(None, description="created_at >= (ISO 8601)"),
    created_to:   Optional[datetime] = Query(None, description="created_at <= (ISO 8601)"),
    method: Optional[MethodT] = Query(None, description="Filter by params.method (JSONB)"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    response: Response = None,
):
    conds = []
    if getattr(user, "role", "user") != "admin":
        if owner_id is not None:
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Permission denied: admin role required")
        conds.append(Job.owner_id == user.id)
    else:
        if owner_id is not None:
            conds.append(Job.owner_id == owner_id)

    if status: conds.append(Job.status == status)
    if file_id is not None: conds.append(Job.file_id == file_id)
    if has_result is True: conds.append(Job.result_id.isnot(None))
    if has_result is False: conds.append(Job.result_id.is_(None))
    if created_from is not None: conds.append(Job.created_at >= created_from)
    if created_to   is not None: conds.append(Job.created_at <= created_to)
    if method is not None: conds.append(Job.params["method"].astext == method)

    allowed_sort = {"created_at": Job.created_at, "id": Job.id, "status": Job.status, "started_at": Job.started_at, "finished_at": Job.finished_at}
    try:
        field, order = (sort.split(":") + ["asc"])[:2]
    except Exception:
        field, order = "created_at", "desc"
    col = allowed_sort.get(field, Job.created_at)
    order_by = col.desc() if str(order).lower() == "desc" else col.asc()

    count_stmt = select(func.count()).select_from(Job)
    if conds:
        count_stmt = count_stmt.where(*conds)
    total = db.scalar(count_stmt)

    offset = (page - 1) * page_size
    list_stmt = select(Job)
    if conds:
        list_stmt = list_stmt.where(*conds)
    list_stmt = list_stmt.order_by(order_by).offset(offset).limit(page_size)
    rows = db.execute(list_stmt).scalars().all()

    items = [{
        "id": j.id,
        "status": j.status,
        "owner_id": j.owner_id,
        "file_id": j.file_id,
        "params": j.params,
        "result_id": j.result_id,
        "created_at": j.created_at.isoformat(),
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    } for j in rows]

    if response is not None:
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Page"] = str(page)
        response.headers["X-Page-Size"] = str(page_size)

    return {"total": total, "page": page, "page_size": page_size, "items": items, "sort": f"{field}:{order}"}


@router.get("/{job_id}", summary="Get a job")
def get_job(job_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "job not found")
    _ensure_owner_or_admin(user, j.owner_id, resource="job")
    return {
        "id": j.id,
        "status": j.status,
        "owner_id": j.owner_id,
        "params": j.params,
        "result_id": j.result_id,
        "created_at": j.created_at.isoformat(),
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    }


@router.get("/results/{result_id}/preview", summary="Get presigned URL for result preview")
def get_preview(result_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    res = db.get(Result, result_id)
    if not res or not res.preview_s3_key:
        raise HTTPException(status_code=404, detail="result not found")
    job = db.query(Job).filter(Job.result_id == res.id).first()
    if not job:
        raise HTTPException(404, "job not found for result")
    _ensure_owner_or_admin(user, job.owner_id, resource="job")
    url = s3_presign_get(res.preview_s3_key)
    return {"url": url, "mime": res.preview_mime, "size": res.preview_size, "etag": res.preview_etag}


@router.delete("/{job_id}", status_code=200, summary="Delete a job")
def delete_job(job_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "job not found")
    _ensure_owner_or_admin(user, j.owner_id, resource="job")
    if j.status == "running":
        raise HTTPException(status_code=409, detail="job is running; stop it before delete")

    db.delete(j)
    db.commit()
    return {"message": "Job deleted successfully", "id": job_id, "deleted_at": datetime.utcnow().isoformat()}
