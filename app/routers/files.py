# app/routers/files.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import File as FileModel
from ..deps import current_user

router = APIRouter(prefix="/v1/files", tags=["files"])

@router.post("/upload", summary="Upload an image (stored in DB)")
async def upload_image(
    f: UploadFile = File(...),
    user=Depends(current_user),
    db: Session = Depends(get_db),
):
    data = await f.read()
    if not data:
        raise HTTPException(400, "empty file")
    rec = FileModel(owner=user["username"], content=data, mime=f.content_type or "image/png")
    db.add(rec); db.commit(); db.refresh(rec)
    return {"id": rec.id, "mime": rec.mime}

@router.get("/{file_id}", summary="Download image (raw bytes)")
def download_image(file_id: int, user=Depends(current_user), db: Session=Depends(get_db)):
    rec = db.query(FileModel).get(file_id)
    if not rec or rec.owner != user["username"]:
        raise HTTPException(404, "file not found")
    from fastapi.responses import StreamingResponse
    import io
    return StreamingResponse(io.BytesIO(rec.content), media_type=rec.mime or "application/octet-stream")
