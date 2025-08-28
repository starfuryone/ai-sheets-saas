from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .db import Base, engine
from .middleware import RequestIDMiddleware
from .routers import ai, auth, credits, stripe, observability

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"]) 
app.include_router(ai.router, prefix="/ai", tags=["ai"]) 
app.include_router(credits.router, prefix="/credits", tags=["credits"]) 
app.include_router(stripe.router, prefix="/stripe", tags=["stripe"]) 

@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# Observability endpoints
app.include_router(observability.router, prefix="/ops", tags=["observability"])
