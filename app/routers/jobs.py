from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from datetime import datetime
from ..db import get_db
from ..models import Job, Result, File
from ..deps import current_user
from ..processing import heavy_pipeline
import cv2, uuid

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])

@router.post("", status_code=201)
def create_job(
    file_id: int,
    repeat: int = 10,
    gamma: float = 0.8,
    use_pretrained: bool = False,
    use_universe_leaf_roi: bool = False,   # ← ROI
    user=Depends(current_user),
    db: Session=Depends(get_db),
):
    f = db.query(File).get(file_id)
    if not f or f.owner != user["username"]:
        raise HTTPException(404, "file not found")

    job = Job(
        file_id=file_id,
        owner=user["username"],
        params={
            "repeat": repeat,
            "gamma": gamma,
            "use_pretrained": use_pretrained,
            "use_universe_leaf_roi": use_universe_leaf_roi,  # ← ROI
        },
    )
    db.add(job); db.commit(); db.refresh(job)
    return {"id": job.id, "status": job.status}

@router.post("/{job_id}/start")
def start_job(job_id: int, user=Depends(current_user), db: Session=Depends(get_db)):
    job = db.query(Job).get(job_id)
    if not job or job.owner != user["username"]:
        raise HTTPException(404, "job not found")
    if job.status not in ("queued","error"):
        return {"status": job.status}

    job.status="running"; job.started_at=datetime.utcnow(); db.commit()
    try:
        # 讀檔路徑（確保在同一個 session 內可用）
        file_rec = db.query(File).get(job.file_id)
        feats, preview, logs = heavy_pipeline(
            file_rec.path,
            repeat=job.params.get("repeat",10),
            gamma=job.params.get("gamma",0.8),
            use_pretrained=job.params.get("use_pretrained", False),
            use_universe_leaf_roi=job.params.get("use_universe_leaf_roi", False),
        )
        prev_path = f"data/storage/{uuid.uuid4().hex}_preview.png"
        cv2.imwrite(prev_path, preview)

        res = Result(summary=feats, preview_path=prev_path, logs=logs)
        db.add(res); db.commit(); db.refresh(res)

        job.result_id=res.id; job.status="done"; job.finished_at=datetime.utcnow(); db.commit()
        return {"status": job.status, "result_id": res.id}
    except Exception as e:
        job.status="error"; db.commit()
        raise HTTPException(500, f"processing failed: {e}")

@router.get("")
def list_jobs(
    status: Optional[str]=None,
    owner: Optional[str]=None,
    sort: str = Query("created_at:desc"),
    page: int=1,
    page_size: int=10,
    user=Depends(current_user),
    db: Session=Depends(get_db)
):
    q = db.query(Job)
    if status: q = q.filter(Job.status==status)
    if owner:  q = q.filter(Job.owner==owner)
    field, order = (sort.split(":")+["asc"])[:2]
    col = getattr(Job, field, Job.created_at)
    q = q.order_by(col.desc() if order=="desc" else col.asc())
    total = q.count()
    items = q.offset((page-1)*page_size).limit(page_size).all()
    return {
        "total": total, "page": page, "page_size": page_size,
        "items": [{"id": j.id, "status": j.status, "owner": j.owner, "created_at": j.created_at.isoformat()} for j in items]
    }

@router.get("/{job_id}")
def get_job(job_id: int, user=Depends(current_user), db: Session=Depends(get_db)):
    j = db.query(Job).get(job_id)
    if not j or j.owner != user["username"]:
        raise HTTPException(404, "job not found")
    return {
        "id": j.id, "status": j.status, "params": j.params, "meta": j.meta, "result_id": j.result_id
    }

# preview
@router.get("/results/{result_id}/preview")
def get_preview(result_id: int, user=Depends(current_user), db: Session=Depends(get_db)):
    res = db.query(Result).get(result_id)
    if not res:
        raise HTTPException(status_code=404, detail="result not found")
    job = db.query(Job).filter(Job.result_id == res.id).first()
    if not job:
        raise HTTPException(404, "job not found for result")
    if job.owner != user["username"] and user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return FileResponse(res.preview_path, media_type="image/png")
