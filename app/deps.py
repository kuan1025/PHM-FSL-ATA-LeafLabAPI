from fastapi import Depends
from db_models import User
from auth import current_user as _current_user, current_admin as _current_admin

def current_user(user: User = Depends(_current_user)) -> User:
    return user

def current_admin(user: User = Depends(_current_admin)) -> User:
    return user
