from sqlalchemy import Column, String
from app.models.base import Base, TimestampMixin, pk


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id = pk()
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    name = Column(String, nullable=False, default="Pooji")
    jocasta_personality = Column(String, default="adaptive")  # adaptive|professional|casual
