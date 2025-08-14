from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException
import os, jwt
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")

def current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return {"username": payload["sub"], "role": payload["role"]}
    except Exception:
        raise HTTPException(401, "Invalid token")

def require_admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return user
