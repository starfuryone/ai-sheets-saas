from pydantic import BaseModel, EmailStr
import uuid

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    is_active: bool

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str
