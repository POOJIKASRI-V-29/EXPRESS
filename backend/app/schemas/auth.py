from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.core.config import settings
from app.schemas.common import ORM


class RegisterIn(BaseModel):
    email: EmailStr
    # bcrypt silently truncates beyond 72 bytes, so the ceiling is explicit
    # rather than something a long passphrase discovers the hard way.
    password: str = Field(min_length=1, max_length=72)
    name: str = Field(default="Pooji", min_length=1, max_length=80)

    @field_validator("password")
    @classmethod
    def _strong_enough(cls, v: str) -> str:
        if len(v) < settings.MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"Password must be at least {settings.MIN_PASSWORD_LENGTH} characters."
            )
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORM):
    id: UUID
    email: str
    name: str
    jocasta_personality: str
