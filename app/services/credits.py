from sqlalchemy.orm import Session
from sqlalchemy import select
from ..models import User, CreditTransaction

def get_balance(db: Session, user_id) -> int:
    user = db.get(User, user_id)
    return user.credits if user else 0

def add_credits(db: Session, user_id, amount: int, description: str = "") -> int:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    user.credits = (user.credits or 0) + amount
    db.add(CreditTransaction(user_id=user_id, amount=amount, description=description))
    db.commit()
    db.refresh(user)
    return user.credits
