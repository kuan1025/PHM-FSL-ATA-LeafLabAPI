# app/routers/auth_cognito.py
import os, time, requests, hmac, hashlib, base64
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends , Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm, HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr
from jose import jwt
import boto3
from fastapi.responses import RedirectResponse
from urllib.parse import quote
from config import settings
import secrets



COGNITO_REGION = settings.COGNITO_REGION
USER_POOL_ID = settings.COGNITO_USER_POOL_ID
CLIENT_ID = settings.COGNITO_CLIENT_ID

CLIENT_SECRET = settings.COGNITO_CLIENT_SECRET

COGNITO_DOMAIN = settings.COGNITO_DOMAIN
REDIRECT_URI = settings.COGNITO_REDIRECT_URI
LOGOUT_REDIRECT_URI = settings.COGNITO_LOGOUT_REDIRECT_URI


router = APIRouter(prefix="/v1/cognito", tags=["auth (Cognito)"])
http_bearer = HTTPBearer(auto_error=True)
cognito = boto3.client("cognito-idp", region_name=COGNITO_REGION)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/cognito/login")

JWKS_URL = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{USER_POOL_ID}/.well-known/jwks.json"

# Https 
COOKIE_DOMAIN = "n11233885.leaflab.cab432.com"  
COOKIE_KW = dict(domain=COOKIE_DOMAIN, path="/", secure=True, httponly=True, samesite="none")



#  cache speed up
_jwks_cache: Dict[str, Any] = {"exp": 0, "keys": []}

# gen cache key
def _get_jwks():
    now = time.time()
    if _jwks_cache["exp"] < now or not _jwks_cache["keys"]:
        try:
            r = requests.get(JWKS_URL, timeout=5)
            r.raise_for_status()
            data = r.json()
            _jwks_cache["keys"] = data.get("keys", [])
            _jwks_cache["exp"] = now + 6 * 3600
        except requests.RequestException:
            if not _jwks_cache["keys"]:
                raise HTTPException(status_code=503, detail="JWKS fetch failed")
    return _jwks_cache["keys"]

def _decode_cognito_jwt(token: str) -> Dict[str, Any]:
    issuer = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{USER_POOL_ID}"
    try:
        headers = jwt.get_unverified_header(token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Malformed token: {e}")

    kid = headers.get("kid")
    key = next((k for k in _get_jwks() if k.get("kid") == kid), None)
    if not key:
        raise HTTPException(status_code=401, detail="JWKS key not found")

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False}
        )
    except Exception:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    token_use = claims.get("token_use")
    if token_use == "id":
        if claims.get("aud") != CLIENT_ID:
            raise HTTPException(status_code=401, detail="Invalid audience")
    elif token_use == "access":
        if claims.get("client_id") != CLIENT_ID:
            raise HTTPException(status_code=401, detail="Invalid client_id")
    else:
        raise HTTPException(status_code=401, detail="Unsupported token type")

    return claims

def cognito_current_user(creds: HTTPAuthorizationCredentials = Depends(http_bearer)) -> dict:
    token = creds.credentials  
    return _decode_cognito_jwt(token) 


def _secret_hash_for(username: str) -> Optional[str]:
    if not CLIENT_SECRET:
        return None
    msg = (username + CLIENT_ID).encode("utf-8")
    key = CLIENT_SECRET.encode("utf-8")
    digest = hmac.new(key, msg, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()

# ---------- Schemas ----------
class SignUpBody(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=8)

class ConfirmBody(BaseModel):
    username: str
    code: str

class TokenOut(BaseModel):
    id_token: str
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int

# ---------- Endpoints ----------
@router.post("/signup", summary="Cognito sign up (email verification)")
def signup(body: SignUpBody):
    kwargs = {
        "ClientId": CLIENT_ID,
        "Username": body.username,
        "Password": body.password,
        "UserAttributes": [{"Name": "email", "Value": body.email}],
    }
    sh = _secret_hash_for(body.username)
    if sh:
        kwargs["SecretHash"] = sh
    try:
        cognito.sign_up(**kwargs)
    except cognito.exceptions.UsernameExistsException:
        raise HTTPException(400, "Username already exists")
    except cognito.exceptions.InvalidPasswordException as e:
        raise HTTPException(400, f"Invalid password policy: {e}")
    return {"message": "Sign-up initiated. Check your email for the confirmation code."}

@router.post("/confirm", summary="Confirm sign up with email code")
def confirm(body: ConfirmBody):
    kwargs = {"ClientId": CLIENT_ID, "Username": body.username, "ConfirmationCode": body.code}
    sh = _secret_hash_for(body.username)
    if sh:
        kwargs["SecretHash"] = sh
    try:
        cognito.confirm_sign_up(**kwargs)
    except cognito.exceptions.CodeMismatchException:
        raise HTTPException(400, "Invalid confirmation code")
    except cognito.exceptions.ExpiredCodeException:
        raise HTTPException(400, "Confirmation code expired")
    return {"message": "User confirmed"}

@router.post("/login", response_model=TokenOut, summary="Login (USER_PASSWORD_AUTH) and return JWTs")
def login(form: OAuth2PasswordRequestForm = Depends()):
    auth_params = {"USERNAME": form.username, "PASSWORD": form.password}
    sh = _secret_hash_for(form.username)
    if sh:
        auth_params["SECRET_HASH"] = sh
    try:
        resp = cognito.initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters=auth_params,
        )
    except cognito.exceptions.NotAuthorizedException:
        raise HTTPException(401, "Incorrect username or password")
    except cognito.exceptions.UserNotConfirmedException:
        raise HTTPException(403, "User not confirmed")
    auth = resp["AuthenticationResult"]
    return TokenOut(
        id_token=auth["IdToken"],
        access_token=auth["AccessToken"],
        refresh_token=auth.get("RefreshToken"),
        token_type="Bearer",
        expires_in=auth["ExpiresIn"],
    )

@router.get("/whoami", summary="Decode current Cognito JWT")
def whoami(user_claims: Dict[str, Any] = Depends(cognito_current_user)):
    return {"claims": user_claims}


# Google id provider

def _basic_auth_header(client_id: str, client_secret: Optional[str]) -> Dict[str, str]:
    if not client_secret:
        return {}
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    return {"Authorization": "Basic " + base64.b64encode(raw).decode("utf-8")}

def _authorize_url(provider: str, state: Optional[str] = None) -> str:
    scopes = "openid+email+profile"
    url = (
        f"{COGNITO_DOMAIN}/oauth2/authorize"
        f"?identity_provider={quote(provider)}"
        f"&response_type=code"
        f"&client_id={quote(CLIENT_ID)}"
        f"&redirect_uri={quote(REDIRECT_URI, safe='')}"
        f"&scope={scopes}"
    )
    if state:
        url += f"&state={quote(state)}"
    return url


@router.get("/login/google", summary="Start Google login via Cognito Hosted UI")
def login_google(response: Response):
    if not (COGNITO_DOMAIN and REDIRECT_URI and CLIENT_ID):
        raise HTTPException(500, "Cognito Hosted UI not configured")

    
    state = secrets.token_urlsafe(24)

    resp = RedirectResponse(_authorize_url("Google", state=state), status_code=302)
    resp.set_cookie("oauth_state", state, **COOKIE_KW)
    return resp

@router.get("/callback", summary="OAuth2 redirect_uri callback (exchange code for tokens)")
def oauth_callback(request: Request, code: str, state: Optional[str] = None):
    if not (COGNITO_DOMAIN and REDIRECT_URI and CLIENT_ID):
        raise HTTPException(500, "Cognito Hosted UI not configured")
    cookie_state = request.cookies.get("oauth_state")
    if not state or state != cookie_state:
        raise HTTPException(400, "Invalid state")

    token_url = f"{COGNITO_DOMAIN}/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    headers.update(_basic_auth_header(CLIENT_ID, CLIENT_SECRET))

    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }

    r = requests.post(token_url, data=data, headers=headers, timeout=10)
    if r.status_code != 200:
        raise HTTPException(400, f"Token exchange failed: {r.text}")

    tokens = r.json()

    from fastapi.responses import JSONResponse
    resp = JSONResponse({"message": "Login with Google via Cognito success", "tokens": tokens})
    resp.delete_cookie("oauth_state", domain=COOKIE_DOMAIN, path="/")
    return resp