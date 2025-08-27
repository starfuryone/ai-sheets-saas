from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func, Boolean
from sqlalchemy.orm import relationship
from app.db import Base
import uuid
from sqlalchemy.dialects.postgresql import UUID

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    credits = relationship("CreditTransaction", back_populates="user")

class CreditTransaction(Base):
    __tablename__ = "credit_transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    description = Column(String)
    created_at = Column(DateTime, default=func.now())
    user = relationship("User", back_populates="credits")

class UsageEvent(Base):
    __tablename__ = "usage_events"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    function_name = Column(String, nullable=False)
    credits_deducted = Column(Integer, nullable=False)
    idempotency_key = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=func.now())
