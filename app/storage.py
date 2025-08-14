import os
from pathlib import Path
STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", "data/storage"))
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
def save_bytes(data: bytes, orig_name: str) -> str:
    from uuid import uuid4
    path = STORAGE_ROOT / f"{uuid4().hex}__{orig_name}"
    with open(path, "wb") as f: f.write(data)
    return str(path)
