from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from ..db import get_db
from ..services.credits import get_balance, add_credits

router = APIRouter()

@router.get('/{user_id}/balance')
def balance(user_id: UUID, db: Session = Depends(get_db)):
    return {"credits": get_balance(db, user_id)}

@router.post('/{user_id}/add')
def add(user_id: UUID, amount: int, db: Session = Depends(get_db)):
    new_balance = add_credits(db, user_id, amount, description="manual grant")
    return {"credits": new_balance}
