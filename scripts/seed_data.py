# Seed example
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models import User

def main():
    db: Session = SessionLocal()
    u = User(email="demo@example.com")
    db.add(u); db.commit()
    print("Seeded demo user:", u.email)

if __name__ == "__main__":
    main()
