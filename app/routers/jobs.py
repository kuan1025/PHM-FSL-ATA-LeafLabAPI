from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi import status as http_status , Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from datetime import datetime
import io
from typing import Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

from db import get_db
from db_models import Job, Result, File, User
from deps import current_user
from processing import heavy_pipeline, decode_image_from_bytes, encode_png

import os

VERSION = os.environ.get("VERSION", "v1")
router = APIRouter(prefix=f"/{VERSION}/jobs", tags=["jobs"])

MethodT  = Literal["sam", "grabcut"]
WBModeT  = Literal["none", "grayworld"]
StatusT  = Literal["queued", "running", "done", "error"]

class CreateJobOptions(BaseModel):
    # Only segmentation is supported. Choose backend via `method`.
    method: MethodT = Field(
        "sam",
        description="Segmentation backend: 'sam' (no preprocessing) or 'grabcut' (optional WB/Gamma).",
    )
    # Preprocessing knobs apply to GrabCut only. Ignored for SAM.
    white_balance: WBModeT = Field(
        "none",
        description="White balance mode (GrabCut only; ignored for SAM).",
    )
    gamma: float = Field(
        1.0,
        description="Gamma (y) correction (GrabCut only; ignored for SAM).",
    )
    repeat: int = Field(
        8, ge=1, le=64,
        description="Repetition count to increase CPU load during segmentation.",
    )


CREATE_JOB_EXAMPLES = {
    "SAM": {
        "summary": "SAM (no preprocessing)",
        "value": {"method": "sam", "repeat": 8},
    },
    "SAM_with_Preproc": {
        "summary": "SAM + preprocessing (shown; ignored by SAM)",
        "value": {"method": "sam", "white_balance": "grayworld", "gamma": 1.12, "repeat": 8},
    },
    "GrabCut": {
        "summary": "GrabCut (no preprocessing)",
        "value": {"method": "grabcut", "white_balance": "none", "gamma": 1.0, "repeat": 8},
    },
    "GrabCut_with_Preproc": {
        "summary": "GrabCut + preprocessing (Grayworld + Gamma)",
        "value": {"method": "grabcut", "white_balance": "grayworld", "gamma": 1.12, "repeat": 8},
    },
}




# ---------- helpers ----------
def _is_admin(user: User) -> bool:
    return getattr(user, "role", "user") == "admin"

def _require_admin(user: User):
    if not _is_admin(user):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Permission denied: admin role required"
        )


def _ensure_owner_or_admin(user: User, owner_id: int, *, resource: str = "job"):
    if _is_admin(user):
        return
    if user.id != owner_id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: not the {resource} owner"
        )

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
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Permission denied: not the file owner"
        )
    job = Job(file_id=file_id, owner_id=user.id, params=body.model_dump())
    db.add(job); db.commit(); db.refresh(job)
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

    job.status = "running"; job.started_at = datetime.utcnow(); db.commit()
    try:
        file_rec = db.get(File, job.file_id)
        if not file_rec or not file_rec.content:
            raise RuntimeError("file content missing")

        img = decode_image_from_bytes(file_rec.content)
        params: Dict[str, Any] = job.params or {}
        method: MethodT = params.get("method", "sam")
        wb: WBModeT = params.get("white_balance", "none")
        gamma: float = float(params.get("gamma", 1.0))
        repeat: int = int(params.get("repeat", 8))
        if method == "sam":
            wb, gamma = "none", 1.0  

        feats, preview, logs = heavy_pipeline(
            img_bgr=img, repeat=repeat, white_balance=wb, gamma=gamma, method=method,
        )

        preview_bytes = encode_png(preview)
        res = Result(summary=feats, preview_bytes=preview_bytes, logs=logs)
        db.add(res); db.commit(); db.refresh(res)

        job.result_id = res.id; job.status = "done"; job.finished_at = datetime.utcnow(); db.commit()
        return {"status": job.status, "result_id": res.id}
    except Exception as e:
        job.status = "error"; db.commit()
        raise HTTPException(500, f"processing failed: {e}")

# -----------------------------
# Admin: requeue
# -----------------------------
class RequeueBody(BaseModel):
    pass

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
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Permission denied: admin role required"
            )
        conds.append(Job.owner_id == user.id)
    else:
        if owner_id is not None:
            conds.append(Job.owner_id == owner_id)


    if status:
        conds.append(Job.status == status)
    if file_id is not None:
        conds.append(Job.file_id == file_id)
    if has_result is True:
        conds.append(Job.result_id.isnot(None))
    if has_result is False:
        conds.append(Job.result_id.is_(None))
    if created_from is not None:
        conds.append(Job.created_at >= created_from)
    if created_to is not None:
        conds.append(Job.created_at <= created_to)
    if method is not None:
        conds.append(Job.params["method"].astext == method)

  
    allowed_sort = {
        "created_at": Job.created_at,
        "id": Job.id,
        "status": Job.status,
        "started_at": Job.started_at,
        "finished_at": Job.finished_at,
    }
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

    items = [
        {
            "id": j.id,
            "status": j.status,
            "owner_id": j.owner_id,
            "file_id": j.file_id,
            "params": j.params,
            "result_id": j.result_id,
            "created_at": j.created_at.isoformat(),
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        }
        for j in rows
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
            "status": status,
            "owner_id": owner_id if getattr(user, "role", "user") == "admin" else None,
            "file_id": file_id,
            "has_result": has_result,
            "created_from": created_from.isoformat() if created_from else None,
            "created_to": created_to.isoformat() if created_to else None,
            "method": method,
        },
    }

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

@router.get("/results/{result_id}/preview", summary="Download result preview")
def get_preview(result_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    res = db.get(Result, result_id)
    if not res or not res.preview_bytes:
        raise HTTPException(status_code=404, detail="result not found")
    job = db.query(Job).filter(Job.result_id == res.id).first()
    if not job:
        raise HTTPException(404, "job not found for result")
    _ensure_owner_or_admin(user, job.owner_id, resource="job")
    return StreamingResponse(io.BytesIO(res.preview_bytes), media_type=res.preview_mime or "image/png")

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

    return {
        "message": "Job deleted successfully",
        "id": job_id,
        "deleted_at": datetime.utcnow().isoformat()
    }
