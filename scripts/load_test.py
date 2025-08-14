import asyncio, httpx, os, pathlib, time
import numpy as np, cv2

BASE = os.getenv("BASE", "http://localhost:8000")
USERNAME = os.getenv("USER", "kuan")
PASSWORD = os.getenv("PASS", "password")
IMG_PATH = os.getenv("IMG", "tests_sample_leaf.jpg")
CONCURRENCY = int(os.getenv("CONCURRENCY", "10"))
DURATION = int(os.getenv("DURATION", "300"))

def ensure_sample(path):
    if pathlib.Path(path).exists(): return
    img = np.zeros((768,1024,3), dtype=np.uint8); img[:]= (80,150,80)
    cv2.circle(img, (512,420), 280, (40,100,40), thickness=40)
    cv2.imwrite(path, img)

async def main():
    async with httpx.AsyncClient(timeout=60.0) as client:
        tok = (await client.post(f"{BASE}/auth/login", data={"username":USERNAME,"password":PASSWORD})).json()["access_token"]
        H = {"Authorization": f"Bearer {tok}"}
        ensure_sample(IMG_PATH)
        with open(IMG_PATH,"rb") as f:
            up = await client.post(f"{BASE}/v1/files", headers=H, files={"f": (pathlib.Path(IMG_PATH).name, f, "image/jpeg")})
        file_id = up.json()["id"]
        jobs=[]
        for _ in range(CONCURRENCY):
            r = await client.post(f"{BASE}/v1/jobs", headers=H, params={"file_id":file_id, "repeat": 16})
            jobs.append(r.json()["id"])
        t_end=time.time()+DURATION
        async def worker(jid):
            while time.time()<t_end:
                await client.post(f"{BASE}/v1/jobs/{jid}/start", headers=H)
        await asyncio.gather(*[worker(j) for j in jobs])

if __name__=="__main__":
    asyncio.run(main())
