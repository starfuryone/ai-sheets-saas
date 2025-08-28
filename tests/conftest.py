import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)
import os
import pytest
from sqlalchemy.orm import Session
from app.db import Base, engine, SessionLocal

@pytest.fixture(scope="session", autouse=True)
def create_test_schema():
    # Ensure tables exist for tests
    Base.metadata.create_all(bind=engine)
    yield
    # Optionally drop tables after tests
    # Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session() -> Session:
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
import os
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.db import SessionLocal
from app.models import User
from app.config import settings as _settings

@pytest.fixture(scope="session", autouse=True)
def _configure_settings_for_tests():
    # Ensure predictable secrets for signing during tests
    _settings.stripe_webhook_secret = "whsec_test_secret"
    _settings.stripe_secret_key = "sk_test_dummy"
    yield

@pytest.fixture
def test_client() -> TestClient:
    return TestClient(app)

@pytest.fixture
def test_user(db_session: Session) -> User:
    user = User(email=f"test_{uuid.uuid4().hex[:8]}@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
