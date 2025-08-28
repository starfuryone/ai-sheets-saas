from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..models import User, CreditTransaction

async def get_balance(db: Session, user_id) -> int:
    user = db.get(User, user_id)
    return user.credits if user else 0

async def add_credits(db: Session, user_id, credits: int, description: str = "", stripe_payment_intent_id: Optional[str] = None, idempotency_key: Optional[str] = None) -> int:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    user.credits = (user.credits or 0) + credits
    db.add(CreditTransaction(user_id=user_id, amount=credits, description=description))
    db.commit()
    db.refresh(user)
    return user.credits
