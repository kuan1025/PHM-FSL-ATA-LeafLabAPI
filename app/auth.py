# app/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import os, jwt
from datetime import datetime, timedelta

router = APIRouter(prefix="/auth", tags=["auth"])

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
ALG = "HS256"

# hardcode   Username / Password 
USERS = {
    "admin": {"password": "admin123", "role": "admin"},
    "kuan":  {"password": "password", "role": "user"},
}

def mk_token(username: str, role: str):
    payload = {"sub": username, "role": role, "exp": datetime.utcnow() + timedelta(hours=8)}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALG)

#  Swagger -> OAuth2（password flow）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def _decode_token(token: str):
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=[ALG])
        return {"username": data["sub"], "role": data.get("role", "user")}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def current_user(token: str = Depends(oauth2_scheme)):
    return _decode_token(token)

# for admin......
def current_admin(user: dict = Depends(current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return user

@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = USERS.get(form.username)
    if not user or user["password"] != form.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad credentials")
    return {"access_token": mk_token(form.username, user["role"]), "token_type": "bearer"}
