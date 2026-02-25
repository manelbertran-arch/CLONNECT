"""Auth models: User, UserCreator."""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

try:
    from api.database import Base
except ImportError:
    from database import Base


class User(Base):
    """User accounts for authentication"""

    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True))


class UserCreator(Base):
    """Many-to-many relationship between Users and Creators"""

    __tablename__ = "user_creators"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False, index=True)
    role = Column(String(50), default="owner")  # owner, admin, viewer
    created_at = Column(DateTime(timezone=True), server_default=func.now())
