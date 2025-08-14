from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import requests
from ..db import get_db
from ..models import Job
from ..deps import current_user

router = APIRouter(prefix="/v1/weather", tags=["external"], dependencies=[Depends(current_user)])

@router.post("/attach/{job_id}")
def attach_weather(job_id: int, lat: float, lon: float, user=Depends(current_user), db: Session=Depends(get_db)):
    job = db.query(Job).get(job_id)
    if not job or job.owner != user["username"]: raise HTTPException(404, "job not found")
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    r = requests.get(url, timeout=10); r.raise_for_status()
    job.meta = (job.meta or {}) | {"weather": r.json().get("current_weather", {})}
    db.commit()
    return {"job_id": job_id, "weather": job.meta["weather"]}
