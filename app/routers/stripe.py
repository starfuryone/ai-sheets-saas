import stripe
import logging
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session

from app.db import get_db
from app.config import settings
from app.services.stripe_events import StripeEventProcessor
from app.models import StripeEventLog

stripe.api_key = settings.stripe_secret_key
router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
    stripe_signature: str = Header(None, alias="stripe-signature")
):
    """Enhanced Stripe webhook handler with database-level idempotency."""
    
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")
    
    # Get raw body for signature verification
    body = await request.body()
    
    try:
        # Verify webhook signature with timestamp tolerance
        event = stripe.Webhook.construct_event(
            body,
            stripe_signature,
            settings.stripe_webhook_secret,
            tolerance=300  # 5 minutes tolerance for timestamp
        )
    except ValueError as e:
        logger.error(f"Invalid payload in webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature in webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Log webhook receipt
    logger.info(f"Received Stripe webhook: {event.get('id')} ({event.get('type')})")
    
    # Process event with idempotency protection
    processor = StripeEventProcessor(db)
    try:
        success, message = await processor.process_event(event)
        
        if not success:
            # Return 400 for client errors, 500 for server errors
            status_code = 400 if "Invalid" in message else 500
            logger.error(f"Webhook processing failed: {message}")
            raise HTTPException(status_code=status_code, detail=message)
        
        logger.info(f"Webhook processed successfully: {event.get('id')}")
        return {"status": "success", "message": message}
        
    except Exception as e:
        logger.error(f"Unexpected error processing webhook {event.get('id')}: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")

@router.get("/events/{event_id}/status")
async def get_event_status(
    event_id: str,
    db: Session = Depends(get_db)
):
    """Get processing status of a Stripe event."""
    event_log = db.query(StripeEventLog).filter(
        StripeEventLog.stripe_event_id == event_id
    ).first()
    
    if not event_log:
        raise HTTPException(status_code=404, detail="Event not found")
    
    return {
        "event_id": event_id,
        "event_type": event_log.event_type,
        "processed": event_log.processed,
        "processing_attempts": event_log.processing_attempts,
        "error_message": event_log.error_message,
        "processed_at": event_log.processed_at,
        "created_at": event_log.created_at,
        "next_retry_at": event_log.next_retry_at if hasattr(event_log, 'next_retry_at') else None
    }

# Keep existing credit pack and checkout endpoints from your current router
