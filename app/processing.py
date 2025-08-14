import time
import cv2
import numpy as np
import os
from skimage.morphology import remove_small_holes, remove_small_objects
from skimage.measure import label
from scipy.ndimage import binary_fill_holes
from segment_anything import SamPredictor, sam_model_registry

# Globally load SAM model (load once at app startup to avoid reloading on each call)
SAM_MODEL_TYPE = "vit_b"
# Dynamically resolve path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAM_CHECKPOINT = os.path.join(BASE_DIR, "..", "models", "sam_vit_b_01ec64.pth")
sam_predictor = None
try:
    if not os.path.exists(SAM_CHECKPOINT):
        raise FileNotFoundError(f"SAM checkpoint not found at {SAM_CHECKPOINT}")
    sam_model = sam_model_registry[SAM_MODEL_TYPE](checkpoint=SAM_CHECKPOINT)
    sam_predictor = SamPredictor(sam_model)
    print(f"SAM model loaded successfully from {SAM_CHECKPOINT}")
except FileNotFoundError as e:
    print(f"Warning: {e}. SAM disabled.")
except Exception as e:
    print(f"Error loading SAM model: {e}. SAM disabled.")

VERSION = "processing-tight-v4-sam-2025-08-14"

# New: Generate mask using SAM
def _sam_mask(bgr: np.ndarray, seed_u8: np.ndarray) -> np.ndarray:
    if sam_predictor is None:
        raise ValueError("SAM model not loaded. Check checkpoint path.")
    
    # Convert to RGB (required by SAM)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    sam_predictor.set_image(rgb)
    
    # Generate bounding box from seed as prompt
    x, y, w, h = _bbox_from_mask(seed_u8, bgr.shape[:2])
    input_box = np.array([x, y, x + w, y + h])  # [x1, y1, x2, y2]
    
    # Predict masks (multiple candidates, select the best)
    masks, scores, _ = sam_predictor.predict(
        box=input_box,
        multimask_output=True  # Generate multiple masks
    )
    
    # Select the mask with the most overlap with the seed
    best_mask = None
    best_overlap = 0
    seed_bool = seed_u8 > 0
    for mask in masks:
        overlap = np.sum(mask & seed_bool)
        if overlap > best_overlap:
            best_overlap = overlap
            best_mask = mask
    
    if best_mask is None:
        best_mask = masks[np.argmax(scores)]  # Fallback: Select highest-scoring mask
    
    return (best_mask.astype(np.uint8) * 255)

# ---------- Seed Generation ----------
def _exgr_map(bgr: np.ndarray) -> np.ndarray:
    B, G, R = cv2.split(bgr)
    exg = 2 * G.astype(np.int16) - R.astype(np.int16) - B.astype(np.int16)
    exr = (1.4 * R.astype(np.float32) - G.astype(np.float32))
    exgr = exg.astype(np.float32) - exr
    exgr = cv2.normalize(exgr, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return exgr

def _exgr_seed(bgr: np.ndarray) -> np.ndarray:
    score = _exgr_map(bgr)
    _, seed = cv2.threshold(score, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    seed = cv2.morphologyEx(seed, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8), 1)
    seed = cv2.morphologyEx(seed, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), 1)
    return seed

def _hsv_green_seed(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    green = ((h >= 25) & (h <= 95) & (s >= 40) & (v >= 30)).astype(np.uint8) * 255
    green = cv2.morphologyEx(green, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), 1)
    return green

def _bbox_from_mask(seed: np.ndarray, shape_hw) -> tuple:
    H, W = shape_hw
    ys, xs = np.where(seed > 0)
    if len(xs) == 0 or len(ys) == 0:
        return (int(W * 0.15), int(H * 0.15), int(W * 0.7), int(H * 0.7))
    x1, x2, y1, y2 = xs.min(), xs.max(), ys.min(), ys.max()
    return (x1, y1, x2 - x1 + 1, y2 - y1 + 1)

# ---------- Cleaning ----------
def _clean_mask_bool(m_bool: np.ndarray, img_hw, k_largest=1) -> np.ndarray:
    H, W = img_hw
    img_area = H * W
    hole_thr = max(0.002 * img_area, 1500)
    obj_thr  = max(0.002 * img_area, 1500)

    m = binary_fill_holes(m_bool)
    m = remove_small_holes(m, area_threshold=hole_thr)
    m = remove_small_objects(m, min_size=obj_thr)

    lbl = label(m)
    if lbl.max() >= k_largest:
        sizes = np.bincount(lbl.ravel()); sizes[0] = 0
        keep = np.zeros_like(m)
        for lab_id in np.argsort(sizes)[::-1][:k_largest]:
            if lab_id == 0: continue
            keep |= (lbl == lab_id)
        m = keep
    return m

# ---------- Secondary GrabCut Refinement (Trimap) ----------
def _refine_with_trimap(bgr: np.ndarray, mask_u8: np.ndarray, seed_u8: np.ndarray,
                        shrink_px: int, iters: int = 3) -> np.ndarray:
    H, W = mask_u8.shape
    k_fg = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (shrink_px * 2 + 1, shrink_px * 2 + 1))
    k_bg = k_fg

    # Sure FG = Erode mask and include seed
    sure_fg = cv2.erode(mask_u8, k_fg, iterations=1)
    sure_fg = cv2.bitwise_or(sure_fg, seed_u8)

    # Sure BG = Inverse of dilated mask
    dil = cv2.dilate(mask_u8, k_bg, iterations=1)
    sure_bg = cv2.bitwise_not(dil)

    # Remaining areas are uncertain
    gc = np.full((H, W), cv2.GC_PR_BGD, np.uint8)
    gc[sure_bg > 0] = cv2.GC_BGD
    gc[mask_u8 > 0] = cv2.GC_PR_FGD
    gc[sure_fg > 0] = cv2.GC_FGD

    bgdModel = np.zeros((1, 65), np.float64)
    fgdModel = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(bgr, gc, None, bgdModel, fgdModel, max(1, iters), cv2.GC_INIT_WITH_MASK)
        leaf2 = (gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)
    except cv2.error:
        leaf2 = mask_u8 > 0

    m2 = _clean_mask_bool(leaf2, (H, W), k_largest=1)
    return (m2.astype(np.uint8)) * 255

# ---------- Main: Leaf Masking ----------
def leaf_mask(
    bgr: np.ndarray,
    rect_pad: float = 0.10,     # Slightly reduce padding to avoid background
    dilate_px: int = 26,        # Seed dilation for initial FGD
    k_largest: int = 1,         # Keep only the largest component
    tight: int = 2,             # 0..4, higher is tighter
    shrink_pct: float = 0.018,  # Erosion/dilation ratio for refinement (relative to image short side)
    use_sam: bool = False       # New: Whether to use SAM
) -> np.ndarray:
    H, W = bgr.shape[:2]

    # Resize image to speed up processing (if image is too large)
    if max(H, W) > 1024:
        scale = 1024 / max(H, W)
        bgr_resized = cv2.resize(bgr, (int(W * scale), int(H * scale)))
    else:
        bgr_resized = bgr

    H_resized, W_resized = bgr_resized.shape[:2]  # Update dimensions

    # 1) Seed (ExGR ∪ HSV)
    seed_exgr = _exgr_seed(bgr_resized)
    seed_green = _hsv_green_seed(bgr_resized)
    seed = cv2.bitwise_or(seed_exgr, seed_green)

    if use_sam and sam_predictor is not None:
        # Use SAM for segmentation
        mask_u8 = _sam_mask(bgr_resized, seed)
    else:
        # Original GrabCut logic
        # 2) PR_FGD rectangle (with padding)
        x, y, w, h = _bbox_from_mask(seed, (H_resized, W_resized))
        pad_x = int(w * rect_pad); pad_y = int(h * rect_pad)
        rx = max(0, x - pad_x); ry = max(0, y - pad_y)
        rw = min(W_resized - rx, w + 2 * pad_x); rh = min(H_resized - ry, h + 2 * pad_y)

        # 3) Prepare GrabCut (first stage)
        gc = np.full((H_resized, W_resized), cv2.GC_PR_BGD, np.uint8)
        border = max(8, int(0.02 * min(H_resized, W_resized)))
        gc[:border, :] = cv2.GC_BGD
        gc[-border:, :] = cv2.GC_BGD
        gc[:, :border] = cv2.GC_BGD
        gc[:, -border:] = cv2.GC_BGD
        gc[ry:ry + rh, rx:rx + rw] = cv2.GC_PR_FGD

        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_px * 2 + 1, dilate_px * 2 + 1))
        sure_fg = cv2.dilate(((seed > 0).astype(np.uint8) * 255), k, iterations=1)
        gc[sure_fg > 0] = cv2.GC_FGD

        bgdModel = np.zeros((1, 65), np.float64)
        fgdModel = np.zeros((1, 65), np.float64)
        try:
            cv2.grabCut(bgr_resized, gc, None, bgdModel, fgdModel, 5, cv2.GC_INIT_WITH_MASK)
            leaf = (gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)
        except cv2.error:
            leaf = (sure_fg > 0)

        # 4) Clean once
        m_clean = _clean_mask_bool(leaf, (H_resized, W_resized), k_largest=k_largest)
        mask_u8 = (m_clean.astype(np.uint8)) * 255

        # 5) Refine based on tight parameter
        if tight <= 0:
            mask_u8 = mask_u8  # Return directly
        else:
            # Basic refinement: Keep component with max overlap with seed + small opening operation
            m = mask_u8 > 0
            s = seed > 0
            lbl = label(m)
            if lbl.max() > 0:
                best_id, best_overlap = 0, -1
                for lab_id in range(1, lbl.max() + 1):
                    ov = int(np.sum((lbl == lab_id) & s))
                    if ov > best_overlap:
                        best_overlap, best_id = ov, lab_id
                m = (lbl == best_id)
            m = cv2.morphologyEx((m.astype(np.uint8) * 255),
                                 cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
                                 iterations=1) > 0
            mask_u8 = (m.astype(np.uint8)) * 255

            # Second stage: Trimap refinement (tighter -> larger shrink)
            if tight >= 1:
                base = min(H_resized, W_resized)
                scale = {1: 1.0, 2: 1.5, 3: 2.0, 4: 2.7}.get(int(tight), 1.5)
                shrink_px = max(1, int(base * shrink_pct * scale))
                mask_u8 = _refine_with_trimap(bgr_resized, mask_u8, seed, shrink_px=shrink_px, iters=3)

            # Extra refinement (for tight >= 3, apply stronger erosion-dilation)
            if tight >= 3:
                k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                mask_u8 = cv2.erode(mask_u8, k3, iterations=1)
                mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN,
                                           cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), 1)

    # Final cleaning (for both SAM and GrabCut)
    m_clean = _clean_mask_bool(mask_u8 > 0, (H_resized, W_resized), k_largest=k_largest)
    mask_u8 = (m_clean.astype(np.uint8)) * 255

    # If resized, restore to original size
    if 'bgr_resized' in locals():
        mask_u8 = cv2.resize(mask_u8, (W, H), interpolation=cv2.INTER_NEAREST)

    return mask_u8

# ---------- Output ----------
def preview_overlay(bgr: np.ndarray, mask_u8: np.ndarray) -> np.ndarray:
    out = bgr.copy()
    leaf = mask_u8 > 0
    out[~leaf] = (out[~leaf] * 0.25).astype(np.uint8)
    overlay = np.zeros_like(out)
    overlay[leaf] = (0, 255, 0)
    return cv2.addWeighted(out, 0.7, overlay, 0.3, 0.0)

def cutout_white(bgr: np.ndarray, mask_u8: np.ndarray) -> np.ndarray:
    out = bgr.copy()
    out[mask_u8 == 0] = 255
    return out

# ---------- Compatible with /v1/jobs ----------
def heavy_pipeline(
    img_path: str,
    *,
    repeat: int = 10,
    gamma: float = 1.0,
    roi_style: str = "leaf",
    use_sam: bool = False,  # New: Support SAM
    **_
):
    t0 = time.time()
    img = cv2.imread(img_path)
    if img is None:
        raise ValueError(f"cannot read image: {img_path}")

    if abs(gamma - 1.0) > 1e-3:
        table = np.array([(i / 255.0) ** gamma * 255 for i in range(256)]).astype("uint8")
        img = cv2.LUT(img, table)

    mask = None
    for _ in range(int(max(1, repeat))):
        mask = leaf_mask(img, tight=3, use_sam=use_sam)

    leaf_px = int((mask > 0).sum())
    total_px = int(img.shape[0] * img.shape[1])
    coverage = float(leaf_px / total_px * 100.0) if total_px else 0.0
    preview = preview_overlay(img, mask)
    t1 = time.time()

    result = {
        "leaf": { "pixels": leaf_px, "coverage_pct": round(coverage, 2) },
        "lesion": { "area_pct": 0.0, "pixels": 0, "count": 0, "severity": "none/mild" },
    }
    return result, preview, f"repeat={repeat}, secs={t1 - t0:.2f}"