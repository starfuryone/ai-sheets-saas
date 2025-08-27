from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import logging

from app.config import settings
from app.db import engine, Base, get_db
from app.middleware import IdempotencyMiddleware, RequestIDMiddleware
from app.routers import ai, auth, credits, stripe

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SaaS Sheets AI Functions",
    description="AI-powered functions for Google Sheets with credit system",
    version="1.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://script.google.com",
        "https://script.googleusercontent.com",
        "https://docs.google.com",
        "https://sheets.google.com"
    ] + (["http://localhost:3000"] if settings.debug else []),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Custom middleware
app.add_middleware(RequestIDMiddleware)
app.add_middleware(IdempotencyMiddleware)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["authentication"])
app.include_router(ai.router, prefix="/ai", tags=["ai-functions"])
app.include_router(credits.router, prefix="/credits", tags=["credits"])
app.include_router(stripe.router, prefix="/stripe", tags=["payments"])

@app.get("/")
async def root():
    return {"message": "SaaS Sheets AI Functions API"}
