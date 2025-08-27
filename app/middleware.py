from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import uuid
import time

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Basic placeholder for idempotency logic
        idempotency_key = request.headers.get("Idempotency-Key")
        if idempotency_key:
            # In a real app, you would check if this key has been seen before
            # and return a cached response if it has.
            pass
        response = await call_next(request)
        return response
