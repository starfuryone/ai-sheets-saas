from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Redis helper
_redis_client = None
def get_redis():
    """Return a Redis client from settings.redis_url."""
    global _redis_client
    if _redis_client is None:
        try:
            import redis  # type: ignore
            from .config import settings as _settings
            _redis_client = redis.Redis.from_url(_settings.redis_url, decode_responses=True)
        except Exception as e:
            raise RuntimeError(f"Redis initialization failed: {e}")
    return _redis_client
