from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_token
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def get_current_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    cred_err = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated",
                            {"WWW-Authenticate": "Bearer"})
    if not token:
        raise cred_err
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise cred_err
        uid = payload.get("sub")
    except Exception:
        raise cred_err
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise cred_err
    return user
