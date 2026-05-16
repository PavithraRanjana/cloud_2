import os
import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

DEFAULT_SECRET = "aerolink-jwt-secret-key-change-in-production"
DEFAULT_ALGORITHM = "HS256"

# Cognito — populated from env vars in ECS; empty = local HS256 mode
_COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
_COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "")
_AWS_REGION = os.environ.get("AWS_REGION", "eu-west-1")
# Set in docker-compose for LocalStack (http://localstack:4566); empty = real AWS
_AWS_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL", "")

# JWKS cache: {kid: raw_key_dict}, refreshed at most once per hour
_jwks_cache: dict = {}
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 3600


def _cognito_issuer() -> str:
    if _AWS_ENDPOINT_URL:
        # LocalStack: JWT issuer matches the LocalStack endpoint
        return f"{_AWS_ENDPOINT_URL}/{_COGNITO_USER_POOL_ID}"
    return f"https://cognito-idp.{_AWS_REGION}.amazonaws.com/{_COGNITO_USER_POOL_ID}"


def _fetch_jwks() -> dict:
    global _jwks_cache, _jwks_fetched_at
    now = time.time()
    if _jwks_cache and (now - _jwks_fetched_at) < _JWKS_TTL:
        return _jwks_cache
    url = f"{_cognito_issuer()}/.well-known/jwks.json"
    resp = httpx.get(url, timeout=5.0)
    resp.raise_for_status()
    keys = resp.json()["keys"]
    _jwks_cache = {k["kid"]: k for k in keys}
    _jwks_fetched_at = now
    return _jwks_cache


def _verify_cognito_token(token: str) -> dict:
    """Validate a Cognito RS256 JWT against the User Pool JWKS. Returns raw claims."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=f"Invalid token header: {e}")

    kid = header.get("kid")
    alg = header.get("alg", "RS256")

    try:
        keys = _fetch_jwks()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"Unable to fetch Cognito JWKS: {e}")

    if kid not in keys:
        # One-shot refresh to handle key rotation
        global _jwks_fetched_at
        _jwks_fetched_at = 0.0
        try:
            keys = _fetch_jwks()
        except Exception:
            pass

    if kid not in keys:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Unknown signing key")

    try:
        claims = jwt.decode(
            token,
            keys[kid],
            algorithms=[alg],
            audience=_COGNITO_CLIENT_ID,
            issuer=_cognito_issuer(),
        )
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=f"Token validation failed: {e}")

    return claims


def _claims_to_user(claims: dict, raw_token: str) -> dict:
    """Map Cognito ID-token claims to the standard user dict used across all services."""
    groups: list[str] = claims.get("cognito:groups") or []
    # First group wins for single-role checks; 'passenger' is the safe default
    role = groups[0] if groups else "passenger"

    full_name = (
        claims.get("name")
        or " ".join(filter(None, [claims.get("given_name"), claims.get("family_name")]))
        or claims.get("cognito:username", "")
    )

    return {
        "sub": claims["sub"],
        "email": claims.get("email", ""),
        "username": claims.get("cognito:username", claims.get("sub")),
        "full_name": full_name,
        "role": role,
        "groups": groups,
        "_token": raw_token,
    }


def _verify_hs256_token(token: str) -> dict:
    """Local dev fallback: verify HS256 token with the shared JWT_SECRET."""
    secret = os.environ.get("JWT_SECRET", DEFAULT_SECRET)
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=f"Invalid token: {e}")


def decode_token(token: str, secret: str = DEFAULT_SECRET,
                 algorithm: str = DEFAULT_ALGORITHM) -> dict:
    """Verify the bearer token and return a normalized user dict.

    Production: RS256 validation against Cognito JWKS.
    Local dev:  HS256 validation against JWT_SECRET (when COGNITO_USER_POOL_ID is unset).
    """
    if _COGNITO_USER_POOL_ID:
        claims = _verify_cognito_token(token)
        return _claims_to_user(claims, token)
    return _verify_hs256_token(token)


# ── Password hashing (auth-service only) ─────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Token creation (auth-service local dev only) ──────────────────────────────

def create_access_token(data: dict, secret: str = DEFAULT_SECRET,
                        algorithm: str = DEFAULT_ALGORITHM,
                        expires_minutes: int = 15) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode["type"] = "access"
    return jwt.encode(to_encode, secret, algorithm=algorithm)


def create_refresh_token(data: dict, secret: str = DEFAULT_SECRET,
                         algorithm: str = DEFAULT_ALGORITHM,
                         expires_days: int = 7) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + timedelta(days=expires_days)
    to_encode["type"] = "refresh"
    return jwt.encode(to_encode, secret, algorithm=algorithm)


# ── FastAPI dependency helpers ────────────────────────────────────────────────

class RoleChecker:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
        user = decode_token(credentials.credentials)
        # Check all Cognito groups the user belongs to, not just the primary role
        groups: list[str] = user.get("groups") or [user.get("role", "passenger")]
        if not any(g in self.allowed_roles for g in groups):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Insufficient permissions")
        return user


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    return decode_token(credentials.credentials)
