import os
import time
import cv2
import numpy as np
from typing import Tuple, Literal, Optional
from skimage.morphology import remove_small_holes, remove_small_objects
from skimage.measure import label
from scipy.ndimage import binary_fill_holes
from segment_anything import SamPredictor, sam_model_registry
from config import settings

# ----------------------------------------------------------------------
# Global SAM
# SAM : Reference to https://github.com/facebookresearch/segment-anything
# Grabcut : Ref -> https://docs.opencv.org/3.4/d8/d83/tutorial_py_grabcut.html
# Grabcut example code :
# ----------------------------------------------------------------------
SAM_MODEL_TYPE = settings.SAM_MODEL_TYPE
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAM_CHECKPOINT = settings.SAM_CHECKPOINT

_sam_predictor: Optional[SamPredictor] = None
try:
    if os.path.exists(SAM_CHECKPOINT):
        _sam_predictor = SamPredictor(sam_model_registry[SAM_MODEL_TYPE](checkpoint=SAM_CHECKPOINT))
        print(f"[processing] SAM loaded: {SAM_MODEL_TYPE} from {SAM_CHECKPOINT}")
    else:
        print(f"[processing] SAM checkpoint not found at {SAM_CHECKPOINT}. SAM disabled.")
except Exception as e:
    _sam_predictor = None
    print(f"[processing] SAM init error: {e}. SAM disabled.")

VERSION = "processing-clean-2025-08-16"

# ----------------------------------------------------------------------
# Utilities: pre-processing (white balance, gamma), kernels, seeds
# ----------------------------------------------------------------------
def _grayworld_wb(bgr: np.ndarray) -> np.ndarray:
    x = bgr.astype(np.float32)
    mean = x.reshape(-1, 3).mean(axis=0)
    scale = mean.mean() / (mean + 1e-6)
    y = np.clip(x * scale, 0, 255).astype(np.uint8)
    return y

def _apply_gamma(bgr: np.ndarray, gamma: float) -> np.ndarray:
    if abs(gamma - 1.0) < 1e-3:
        return bgr
    table = np.array([(i / 255.0) ** gamma * 255 for i in range(256)], dtype=np.uint8)
    return cv2.LUT(bgr, table)

def _kernel_by_ratio(short_side: int, ratio: float, odd_min: int = 3, odd_max: int = 21):
    k = int(max(odd_min, min(odd_max, round(short_side * ratio))))
    if k % 2 == 0:
        k += 1
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))

def _exgr_map(bgr: np.ndarray) -> np.ndarray:
    B, G, R = cv2.split(bgr)
    exg = 2 * G.astype(np.int16) - R.astype(np.int16) - B.astype(np.int16)
    exr = (1.4 * R.astype(np.float32) - G.astype(np.float32))
    exgr = exg.astype(np.float32) - exr
    exgr = cv2.normalize(exgr, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return exgr

def _exgr_seed(bgr: np.ndarray, open_k, close_k) -> np.ndarray:
    score = _exgr_map(bgr)
    _, seed = cv2.threshold(score, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    seed = cv2.morphologyEx(seed, cv2.MORPH_OPEN, open_k, 1)
    seed = cv2.morphologyEx(seed, cv2.MORPH_CLOSE, close_k, 1)
    return seed

def _hsv_green_seed(bgr: np.ndarray, open_k) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    green = ((h >= 25) & (h <= 95) & (s >= 40) & (v >= 30)).astype(np.uint8) * 255
    return cv2.morphologyEx(green, cv2.MORPH_OPEN, open_k, 1)

def _bbox_from_mask(seed: np.ndarray, shape_hw: Tuple[int, int]) -> Tuple[int, int, int, int]:
    H, W = shape_hw
    ys, xs = np.where(seed > 0)
    if len(xs) == 0 or len(ys) == 0:
        # fallback: centered box (70% area)
        return (int(W * 0.15), int(H * 0.15), int(W * 0.7), int(H * 0.7))
    x1, x2, y1, y2 = xs.min(), xs.max(), ys.min(), ys.max()
    return (x1, y1, x2 - x1 + 1, y2 - y1 + 1)

# ----------------------------------------------------------------------
# Cleaning & post
# ----------------------------------------------------------------------
def _clean_mask_bool(m_bool: np.ndarray, img_hw, k_largest=1) -> np.ndarray:
    H, W = img_hw
    img_area = H * W
    hole_thr = max(0.002 * img_area, 1500)
    obj_thr = max(0.002 * img_area, 1500)

    m = binary_fill_holes(m_bool)
    m = remove_small_holes(m, area_threshold=hole_thr)
    m = remove_small_objects(m, min_size=obj_thr)

    lbl = label(m)
    if lbl.max() >= k_largest:
        sizes = np.bincount(lbl.ravel()); sizes[0] = 0
        keep = np.zeros_like(m)
        for lab_id in np.argsort(sizes)[::-1][:k_largest]:
            keep |= (lbl == lab_id)
        m = keep
    return m

def _refine_with_trimap_strict(
    bgr: np.ndarray,
    mask_u8: np.ndarray,
    seed_u8: np.ndarray,
    *,
    shrink_px: int,
    iters: int = 3
) -> np.ndarray:
    """
    Second-pass GrabCut refinement using a conservative trimap:
    - sure FG: eroded mask (+ seed union)
    - sure BG: inverse of dilated mask
    - uncertain: remaining
    """
    H, W = mask_u8.shape
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (shrink_px * 2 + 1, shrink_px * 2 + 1))

    sure_fg = cv2.erode(mask_u8, k, iterations=1)
    if seed_u8 is not None:
        sure_fg = cv2.bitwise_or(sure_fg, seed_u8)

    dil = cv2.dilate(mask_u8, k, iterations=1)
    sure_bg = cv2.bitwise_not(dil)

    gc = np.full((H, W), cv2.GC_PR_BGD, np.uint8)
    gc[sure_bg > 0] = cv2.GC_BGD
    gc[mask_u8 > 0] = cv2.GC_PR_FGD
    gc[sure_fg > 0] = cv2.GC_FGD

    bgdModel = np.zeros((1, 65), np.float64)
    fgdModel = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(bgr, gc, None, bgdModel, fgdModel, max(1, iters), cv2.GC_INIT_WITH_MASK)
        leaf = (gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)
    except cv2.error:
        leaf = mask_u8 > 0

    m2 = _clean_mask_bool(leaf, (H, W), k_largest=1)
    return (m2.astype(np.uint8)) * 255

def preview_focus(bgr: np.ndarray, mask_u8: np.ndarray, *, dim_bg: float = 0.25, outline: bool = False) -> np.ndarray:
    """
    Visualization that keeps foreground colors intact:
    - Dims background by `dim_bg`
    - Optionally draws a thin outline (disabled by default)
    """
    out = bgr.copy()
    fg = mask_u8 > 0
    out[~fg] = (out[~fg] * float(dim_bg)).astype(np.uint8)
    if outline:
        contours, _ = cv2.findContours((mask_u8 > 0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(out, contours, -1, (0, 255, 0), thickness=2)
    return out

def cutout_white(bgr: np.ndarray, mask_u8: np.ndarray) -> np.ndarray:
    out = bgr.copy()
    out[mask_u8 == 0] = 255
    return out

# ----------------------------------------------------------------------
# Segmentation backends: SAM / GrabCut 
# ----------------------------------------------------------------------
def _best_mask_by_iou(masks: np.ndarray, seed_bool: np.ndarray, scores: np.ndarray) -> np.ndarray:
    best_idx = -1
    best_iou = -1.0
    seed_area = seed_bool.sum()
    # Select Best IOU
    for i, m in enumerate(masks):
        inter = np.logical_and(m, seed_bool).sum()
        union = m.sum() + seed_area - inter
        iou = (inter / union) if union > 0 else 0.0
        
        if iou > best_iou:
            best_iou = iou
            best_idx = i
    if best_idx < 0:
        best_idx = int(np.argmax(scores))
    return masks[best_idx]

def _segment_with_sam(bgr: np.ndarray, seed_u8: np.ndarray) -> np.ndarray:
    if _sam_predictor is None:
        raise ValueError("SAM model not loaded. Check checkpoint path or disable SAM.")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    # bounding box -->>
    _sam_predictor.set_image(rgb)

    x, y, w, h = _bbox_from_mask(seed_u8, bgr.shape[:2])
    input_box = np.array([x, y, x + w, y + h])
    
    ys, xs = np.where(seed_u8 > 0)
    if len(xs) and len(ys):
        pt = np.array([[xs.mean(), ys.mean()]], dtype=np.float32)
        pl = np.array([1], dtype=np.int32)
        #  ->> predict
        masks, scores, _ = _sam_predictor.predict(
            point_coords=pt, point_labels=pl, box=input_box, multimask_output=True
        )
    else:
        masks, scores, _ = _sam_predictor.predict(box=input_box, multimask_output=True)

    best = _best_mask_by_iou(masks, (seed_u8 > 0), scores)
    return (best.astype(np.uint8) * 255)

def _segment_with_grabcut(
    bgr: np.ndarray,
    seed_u8: np.ndarray,
    *,
    rect_pad: float = 0.08,       # slightly tighter than before
    dilate_ratio: float = 0.018,  # bg ring
    iters_first: int = 7,
    iters_refine: int = 5
) -> np.ndarray:
    """
    Two-stage (strict) GrabCut:
    1) Initial GrabCut with conservative sure-FG and sure-BG
    2) Trimap-based refinement to tighten edges and remove residue
    """
    H, W = bgr.shape[:2]
    short = min(H, W)

    # 1) Build initial GC mask
    x, y, w, h = _bbox_from_mask(seed_u8, (H, W))
    pad_x, pad_y = int(w * rect_pad), int(h * rect_pad)
    rx, ry = max(0, x - pad_x), max(0, y - pad_y)
    rw, rh = min(W - rx, w + 2 * pad_x), min(H - ry, h + 2 * pad_y)

    gc = np.full((H, W), cv2.GC_PR_BGD, np.uint8)

    # Strong frame background
    border = max(8, int(0.02 * short))
    gc[:border, :] = cv2.GC_BGD; gc[-border:, :] = cv2.GC_BGD
    gc[:, :border] = cv2.GC_BGD; gc[:, -border:] = cv2.GC_BGD

    # Region of interest as probable FG
    gc[ry:ry + rh, rx:rx + rw] = cv2.GC_PR_FGD

    # Conservative sure FG (eroded seed)
    erode_px = max(1, int(short * 0.006))
    k_fg = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (erode_px * 2 + 1, erode_px * 2 + 1))
    sure_fg = cv2.erode(seed_u8, k_fg, iterations=1)
    gc[sure_fg > 0] = cv2.GC_FGD

    # Sure BG = inverse of dilated seed
    dilate_px = max(1, int(short * dilate_ratio))
    k_bg = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_px * 2 + 1, dilate_px * 2 + 1))
    sure_bg = cv2.dilate(seed_u8, k_bg, iterations=1)
    sure_bg = cv2.bitwise_not(sure_bg)
    gc[sure_bg > 0] = cv2.GC_BGD

    # First GrabCut pass
    bgdModel = np.zeros((1, 65), np.float64)
    fgdModel = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(bgr, gc, None, bgdModel, fgdModel, max(1, iters_first), cv2.GC_INIT_WITH_MASK)
        leaf1 = (gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)
    except cv2.error:
        leaf1 = sure_fg > 0

    m1 = _clean_mask_bool(leaf1, (H, W), k_largest=1)
    m1_u8 = (m1.astype(np.uint8)) * 255

    # 2) Trimap refinement (strict)
    shrink_px = max(1, int(short * 0.02))  # 2% short side
    m2_u8 = _refine_with_trimap_strict(
        bgr, m1_u8, seed_u8, shrink_px=shrink_px, iters=iters_refine
    )

    # Final polish: small erosion + open to remove wisps
    k_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    m2_u8 = cv2.erode(m2_u8, k_small, iterations=1)
    m2_u8 = cv2.morphologyEx(
        m2_u8, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), 1
    )

    return m2_u8

# ----------------------------------------------------------------------
# Public API: leaf_mask（method: "sam" | "grabcut"）＋preprocess
#   - interface
# ----------------------------------------------------------------------
def leaf_mask(
    bgr: np.ndarray,
    *,
    method: Literal["sam", "grabcut"] = "grabcut",
    white_balance: Literal["none", "grayworld"] = "none",
    gamma: float = 1.0,
    k_largest: int = 1,
    use_sam: Optional[bool] = None  # for backward compatibility with existing routes
) -> np.ndarray:
    # choose backend
    if use_sam is not None:
        method = "sam" if use_sam else "grabcut"

    # preprocess
    if white_balance == "grayworld":
        bgr = _grayworld_wb(bgr)
    if abs(gamma - 1.0) > 1e-3:
        bgr = _apply_gamma(bgr, gamma)

 
    H0, W0 = bgr.shape[:2]
    scale = 1.0
    if max(H0, W0) > 1024:
        scale = 1024 / max(H0, W0)
        bgr_small = cv2.resize(bgr, (int(W0 * scale), int(H0 * scale)))
    else:
        bgr_small = bgr

    H, W = bgr_small.shape[:2]
    short = min(H, W)
    open_k  = _kernel_by_ratio(short, 0.003)
    close_k = _kernel_by_ratio(short, 0.008)
    # -> Generate!!
    seed = cv2.bitwise_or(_exgr_seed(bgr_small, open_k, close_k),
                          _hsv_green_seed(bgr_small, open_k))

    # segment
    if method == "sam":
        mask_small = _segment_with_sam(bgr_small, seed)
    else:
        mask_small = _segment_with_grabcut(bgr_small, seed)

    # keep top-k components 
    m_clean = _clean_mask_bool(mask_small > 0, (H, W), k_largest=k_largest)
    mask_small = (m_clean.astype(np.uint8)) * 255

    # restore size
    if scale != 1.0:
        mask = cv2.resize(mask_small, (W0, H0), interpolation=cv2.INTER_NEAREST)
    else:
        mask = mask_small
    return mask

# ----------------------------------------------------------------------
# Heavy pipeline:  /v1/jobs
#   - add white_balance/gamma/method parameters
# ----------------------------------------------------------------------
def heavy_pipeline(
    img_path: Optional[str] = None,
    *,
    img_bgr=None,                     
    repeat: int = 10,
    gamma: float = 1.0,
    white_balance: Literal["none", "grayworld"] = "none",
    roi_style: str = "leaf",
    use_sam: bool = False,
    method: Optional[Literal["sam","grabcut"]] = None,
    **_
):
    if method is None:
        method = "sam" if use_sam else "grabcut"
    t0 = time.time()
    
    if img_bgr is None:

        img = cv2.imread(img_path)
        if img is None:
            raise ValueError(f"cannot read image: {img_path}")
    else:
        img = img_bgr

    mask = None
    for _ in range(int(max(1, repeat))):
        mask = leaf_mask(img, method=method, white_balance=white_balance, gamma=gamma, k_largest=1)

    leaf_px = int((mask > 0).sum())
    total_px = int(img.shape[0] * img.shape[1])
    coverage = float(leaf_px / total_px * 100.0) if total_px else 0.0

    if method == "sam":
        preview = preview_focus(img, mask, dim_bg=0.25, outline=False)
    else:
        preview = cutout_white(img, mask)

    t1 = time.time()
    result = {
        "leaf": {"pixels": leaf_px, "coverage_pct": round(coverage, 2)},
        "lesion": {"area_pct": 0.0, "pixels": 0, "count": 0, "severity": "none/mild"},
    }
    return result, preview, f"method={method}, repeat={repeat}, wb={white_balance}, gamma={gamma}, secs={t1 - t0:.2f}"



def decode_image_from_bytes(b: bytes):
    arr = np.frombuffer(b, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("invalid image bytes (cannot decode)")
    return img

def encode_png(img) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("failed to encode PNG")
    return buf.tobytes()