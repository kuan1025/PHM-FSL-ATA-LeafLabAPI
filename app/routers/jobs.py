from __future__ import annotations
from typing import Optional, Literal, List, Dict, Any
from datetime import datetime
import io

 
from fastapi import APIRouter, Depends, HTTPException, Query, status, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from db import get_db
from db_models import Job, Result, File
from deps import current_user
from processing import heavy_pipeline, decode_image_from_bytes, encode_png

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])

# -----------------------------
# Schemas (render as dropdowns in Swagger)
# -----------------------------
from pydantic import BaseModel, Field

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

class BatchJobOptions(BaseModel):
    method: MethodT = "sam"
    white_balance: WBModeT = "none"
    gamma: float = 1.0
    repeat: int = Field(8, ge=1, le=64)


# -----------------------------
# OpenAPI example payloads (exactly 4 options)
# -----------------------------
CREATE_JOB_EXAMPLES = {
    # 1) SAM (no preprocessing)
    "SAM": {
        "summary": "SAM (no preprocessing)",
        "value": {"method": "sam", "repeat": 8},
    },
    # 2) SAM + preprocessing (shown, but SAM will still ignore WB/Gamma)
    "SAM_with_Preproc": {
        "summary": "SAM + preprocessing (shown; ignored by SAM)",
        "value": {"method": "sam", "white_balance": "grayworld", "gamma": 1.12, "repeat": 8},
    },
    # 3) GrabCut (no preprocessing)
    "GrabCut": {
        "summary": "GrabCut (no preprocessing)",
        "value": {"method": "grabcut", "white_balance": "none", "gamma": 1.0, "repeat": 8},
    },
    # 4) GrabCut + preprocessing
    "GrabCut_with_Preproc": {
        "summary": "GrabCut + preprocessing (Grayworld + Gamma)",
        "value": {"method": "grabcut", "white_balance": "grayworld", "gamma": 1.12, "repeat": 8},
    },
}


# -----------------------------
# Create (single) — file_id as query input
# -----------------------------
@router.post(
    "",
    status_code=201,
    summary="Create a job (segment)",
    description="`file_id` is a query parameter. Options are provided in the JSON body.",
)
def create_job(
    file_id: int = Query(..., description="ID of the file to process"),
    body: CreateJobOptions = Body(..., openapi_examples=CREATE_JOB_EXAMPLES),
    user=Depends(current_user),
    db: Session = Depends(get_db),
):
    f = db.query(File).get(file_id)
    if not f or f.owner != user["username"]:
        raise HTTPException(404, "file not found")
    job = Job(file_id=file_id, owner=user["username"], params=body.model_dump())
    db.add(job); db.commit(); db.refresh(job)
    return {"id": job.id, "status": job.status, "params": job.params}


# -----------------------------
# Start (single, synchronous)
# -----------------------------
@router.post(
    "/{job_id}/start",
    summary="Start a job (single, synchronous)",
    description="Executes the job immediately and returns the result id (if successful).",
)
def start_job(job_id: int, user=Depends(current_user), db: Session=Depends(get_db)):
    job = db.query(Job).get(job_id)
    if not job or job.owner != user["username"]:
        raise HTTPException(404, "job not found")
    if job.status not in ("queued", "error"):
        return {"status": job.status, "result_id": job.result_id}

    job.status = "running"; job.started_at = datetime.utcnow(); db.commit()
    try:
        file_rec = db.query(File).get(job.file_id)
        if not file_rec or not file_rec.content:
            raise RuntimeError("file content missing")
        img = decode_image_from_bytes(file_rec.content)

        params: Dict[str, Any] = job.params or {}
        method: MethodT = params.get("method", "sam")
        wb: WBModeT = params.get("white_balance", "none")
        gamma: float = float(params.get("gamma", 1.0))
        repeat: int = int(params.get("repeat", 8))

        # Force SAM = no preprocessing
        if method == "sam":
            wb, gamma = "none", 1.0

        feats, preview, logs = heavy_pipeline(
            img_bgr=img,                # <-- use in-memory image
            repeat=repeat,
            white_balance=wb,
            gamma=gamma,
            method=method,
        )

        preview_bytes = encode_png(preview)  # <-- store preview in DB
        res = Result(summary=feats, preview_bytes=preview_bytes, logs=logs)
        db.add(res); db.commit(); db.refresh(res)

        job.result_id = res.id; job.status = "done"; job.finished_at = datetime.utcnow(); db.commit()
        return {"status": job.status, "result_id": res.id}

    except Exception as e:
        job.status = "error"; db.commit()
        raise HTTPException(500, f"processing failed: {e}")

# -----------------------------
# List / Get / Preview
# -----------------------------
@router.get(
    "",
    summary="List jobs",
    description="Supports filtering by status/owner, sorting and pagination.",
)
def list_jobs(
    status: Optional[StatusT] = Query(None, description="Filter by job status."),
    owner: Optional[str]   = Query(None, description="Filter by owner."),
    sort: str              = Query("created_at:desc", description="field:order, e.g. created_at:desc"),
    page: int              = Query(1, ge=1),
    page_size: int         = Query(10, ge=1, le=100),
    user=Depends(current_user),
    db: Session=Depends(get_db),
):
    q = db.query(Job)
    if status: q = q.filter(Job.status == status)
    if owner:  q = q.filter(Job.owner == owner)
    field, order = (sort.split(":") + ["asc"])[:2]
    col = getattr(Job, field, Job.created_at)
    q = q.order_by(col.desc() if order == "desc" else col.asc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total, "page": page, "page_size": page_size,
        "items": [{"id": j.id, "status": j.status, "owner": j.owner, "created_at": j.created_at.isoformat(), "params": j.params} for j in items],
    }

@router.get(
    "/{job_id}",
    summary="Get a job",
    description="Returns job status, parameters and result id (if finished).",
)
def get_job(job_id: int, user=Depends(current_user), db: Session=Depends(get_db)):
    j = db.query(Job).get(job_id)
    if not j or j.owner != user["username"]:
        raise HTTPException(404, "job not found")
    return {
        "id": j.id, "status": j.status, "params": j.params,
        "result_id": j.result_id, "created_at": j.created_at.isoformat(),
    }

@router.get(
    "/results/{result_id}/preview",
    summary="Download result preview",
    description="Requires owner or admin permission.",
)
def get_preview(result_id: int, user=Depends(current_user), db: Session=Depends(get_db)):
    res = db.query(Result).get(result_id)
    if not res or not res.preview_bytes:
        raise HTTPException(status_code=404, detail="result not found")
    job = db.query(Job).filter(Job.result_id == res.id).first()
    if not job:
        raise HTTPException(404, "job not found for result")
    if job.owner != user["username"] and user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return StreamingResponse(io.BytesIO(res.preview_bytes), media_type=res.preview_mime or "image/png")
