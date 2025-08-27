from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db

router = APIRouter()

@router.get("/balance")
async def get_credit_balance(db: Session = Depends(get_db)):
    # Placeholder for getting credit balance
    return {"balance": 100} # Dummy value
