import io
import cv2
import numpy as np
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Query, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import File as FileModel
from ..processing import leaf_mask, preview_overlay, cutout_white, VERSION as PROCESSING_VERSION

router = APIRouter(prefix="/v1/leaf", tags=["leaf"])

def _respond_image_png(arr: np.ndarray) -> StreamingResponse:
    ok, buf = cv2.imencode(".png", arr)
    if not ok:
        raise HTTPException(500, "failed to encode image")
    return StreamingResponse(io.BytesIO(buf.tobytes()), media_type="image/png")

def _segment_and_encode(img_bgr: np.ndarray, mode: str, tight: int, use_sam: bool):
    try:
        mask = leaf_mask(img_bgr, tight=tight, use_sam=use_sam)  # 傳遞 use_sam
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"segmentation error: {e}")

    if mode == "mask":
        return _respond_image_png(mask)
    if mode == "alpha":
        rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2BGRA)
        rgba[:, :, 3] = mask
        return _respond_image_png(rgba)
    if mode == "white":
        cut = cutout_white(img_bgr, mask)
        return _respond_image_png(cut)

    prev = preview_overlay(img_bgr, mask)
    return _respond_image_png(prev)

@router.get("/version")
def version(user=Depends(current_user)):
    return {"processing_version": PROCESSING_VERSION}

@router.post("/segment")
def segment_upload(
    mode: str = Query("white", enum=["mask", "alpha", "white", "preview"]),
    tight: int = Query(3, ge=0, le=4, description="0=loose, 4=very tight"),
    use_sam: bool = Query(False, description="Use Segment Anything for better field segmentation"),  # 新增
    style: Optional[str] = Query(None, description="kept for backward compatibility; ignored"),
    user=Depends(current_user),
    file: UploadFile = File(...),
):
    data = file.file.read()
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "invalid image")
    return _segment_and_encode(img, mode, tight, use_sam)

@router.post("/segment/by-file")
def segment_by_file(
    file_id: int,
    mode: str = Query("white", enum=["mask", "alpha", "white", "preview"]),
    tight: int = Query(3, ge=0, le=4, description="0=loose, 4=very tight"),
    use_sam: bool = Query(False, description="Use Segment Anything for better field segmentation"),  # 新增
    style: Optional[str] = Query(None, description="kept for backward compatibility; ignored"),
    user=Depends(current_user),
    db: Session = Depends(get_db),
):
    rec = db.query(FileModel).get(file_id)
    if not rec or rec.owner != user["username"]:
        raise HTTPException(404, "file not found")
    img = cv2.imread(rec.path)
    if img is None:
        raise HTTPException(400, "cannot read stored image")
    return _segment_and_encode(img, mode, tight, use_sam)