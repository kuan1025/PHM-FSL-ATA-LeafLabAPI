from fastapi import APIRouter, UploadFile, File as UFile, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import File
from ..deps import current_user
from ..storage import save_bytes

router = APIRouter(prefix="/v1/files", tags=["files"], dependencies=[Depends(current_user)])

@router.post("", status_code=201)
def upload(f: UploadFile = UFile(...), user=Depends(current_user), db: Session=Depends(get_db)):
    content = f.file.read()
    path = save_bytes(content, f.filename)
    rec = File(owner=user["username"], orig_name=f.filename, path=path, mime=f.content_type or "application/octet-stream")
    db.add(rec); db.commit(); db.refresh(rec)
    return {"id": rec.id, "name": rec.orig_name}
