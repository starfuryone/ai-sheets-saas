from datetime import datetime, timedelta
import jwt
from .config import settings

def create_access_token(sub: str, expires_minutes: int = 60) -> str:
    payload = {
        "sub": sub,
        "exp": datetime.utcnow() + timedelta(minutes=expires_minutes),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
