from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import require_admin

router = APIRouter(prefix="/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])

@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    total_files  = db.execute("SELECT COUNT(*) FROM files").scalar()
    total_jobs   = db.execute("SELECT COUNT(*) FROM jobs").scalar()
    total_done   = db.execute("SELECT COUNT(*) FROM jobs WHERE status='done'").scalar()
    return {"files": total_files, "jobs": total_jobs, "done": total_done}
