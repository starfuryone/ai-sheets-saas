from pydantic import BaseModel, EmailStr
from typing import Optional

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserCreate(BaseModel):
    email: EmailStr

class UserOut(BaseModel):
    id: str
    email: EmailStr
    class Config:
        from_attributes = True

class CreditBalance(BaseModel):
    credits: int
