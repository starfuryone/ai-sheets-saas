from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import uuid4
from ..db import get_db, Base
from ..models import User
from ..schemas import UserCreate, UserOut, Token
from ..auth import create_access_token

router = APIRouter()

@router.post('/signup', response_model=UserOut)
def signup(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        return existing
    user = User(email=payload.email)
    db.add(user); db.commit(); db.refresh(user)
    return user

@router.post('/login', response_model=Token)
def login(payload: UserCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(str(user.id))
    return Token(access_token=token)
