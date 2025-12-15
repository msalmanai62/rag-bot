from typing import Optional
from fastapi import HTTPException, Depends
import jwt
from app.settings import settings


class JWTAuthenticator:
    def __init__(self, secret: str = settings.JWT_SECRET, algorithm: str = settings.JWT_ALGORITHM):
        self.secret = secret
        self.algorithm = algorithm

    def decode_token(self, token: str) -> Optional[dict]:
        try:
            return jwt.decode(token, self.secret, algorithms=[self.algorithm])
        except Exception:
            return None


auth = JWTAuthenticator()


def get_current_user(token: str = Depends(lambda: None)):
    # Lightweight placeholder. In real apps, use OAuth/JWT header extraction.
    # Here we accept a token payload dict for simplicity in testing.
    raise HTTPException(status_code=401, detail="Not implemented: attach JWT via dependency override")
