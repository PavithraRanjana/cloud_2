from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

DEFAULT_SECRET = "aerolink-jwt-secret-key-change-in-production"
DEFAULT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


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


def decode_token(token: str, secret: str = DEFAULT_SECRET,
                 algorithm: str = DEFAULT_ALGORITHM) -> dict:
    try:
        return jwt.decode(token, secret, algorithms=[algorithm])
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=f"Invalid token: {e}")


class RoleChecker:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, credentials: HTTPAuthorizationCredentials = Depends(security)):
        payload = decode_token(credentials.credentials)
        role = payload.get("role", "passenger")
        if role not in self.allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Insufficient permissions")
        return payload


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    return decode_token(credentials.credentials)
