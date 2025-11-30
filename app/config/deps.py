from typing import Dict, Any, List
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from config.db import get_db
from config.db_models import User
from routers.auth_cognito import cognito_current_user  

def _role_from_claims(claims: Dict[str, Any]) -> str:
    groups: List[str] = claims.get("cognito:groups", []) or []
    return "admin" if ("Admin" in groups) else "user"

def current_user(db: Session = Depends(get_db), claims: Dict[str, Any] = Depends(cognito_current_user)) -> User:
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing sub in token")

    username = claims.get("cognito:username") or claims.get("email") or sub
    email = claims.get("email")
    role = _role_from_claims(claims)

    u = db.query(User).filter(User.cognito_sub == sub).first()
    if not u:
        u = User(cognito_sub=sub, username=username, email=email, role=role)
        db.add(u); db.commit(); db.refresh(u)
    else:
        changed = False
        if u.username != username: u.username, changed = username, True
        if u.email != email: u.email, changed = email, True
        if u.role != role: u.role, changed = role, True
        if changed: db.commit()
    return u

def current_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only")
    return user
