import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    credits = Column(Integer, default=0)

class CreditTransaction(Base):
    __tablename__ = "credit_transactions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    amount = Column(Integer, nullable=False)  # +/- credits
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class UsageEvent(Base):
    __tablename__ = "usage_events"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    endpoint = Column(String(120), nullable=False)
    success = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())



class StripeEventLog(Base):
    __tablename__ = "stripe_event_log"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stripe_event_id = Column(String(255), unique=True, index=True, nullable=False)
    event_type = Column(String(100), nullable=False)
    event_data = Column(Text)  # For simplicity; switch to JSON if using PostgreSQL JSON
    processed = Column(Boolean, default=False, nullable=False)
    processing_attempts = Column(Integer, default=0)
    error_message = Column(Text)
    processed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
class StripeEventLog(Base):
    """Track processed Stripe webhook events for idempotency."""
    __tablename__ = "stripe_event_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stripe_event_id = Column(String(255), unique=True, nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    event_data = Column(JSON)
    processed = Column(Boolean, default=False, nullable=False)
    processing_attempts = Column(Integer, default=0)
    error_message = Column(Text)
    processed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_stripe_event_processed", "processed", "created_at"),
        Index("ix_stripe_event_type", "event_type"),
    )
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Index, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

class StripeEventLog(Base):
    """Track processed Stripe webhook events for idempotency."""
    __tablename__ = "stripe_event_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stripe_event_id = Column(String(255), unique=True, nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    event_data = Column(JSON)  # Store event data for debugging
    processed = Column(Boolean, default=False, nullable=False)
    processing_attempts = Column(Integer, default=0)
    error_message = Column(Text)
    processed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_stripe_event_processed", "processed", "created_at"),
        Index("ix_stripe_event_type", "event_type"),
    )
