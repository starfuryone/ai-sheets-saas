from typing import Dict, Any, Tuple, Optional
import logging
import math
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
import uuid

from app.models import StripeEventLog, User, CreditTransaction
from app.services.credits import add_credits

logger = logging.getLogger(__name__)

class StripeEventProcessor:
    """Process Stripe webhook events with guaranteed idempotency and transactional safety."""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def process_event(self, event_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Process Stripe webhook event with atomic insert-first idempotency.
        
        Returns:
            (success, message)
        """
        event_id = event_data.get("id")
        event_type = event_data.get("type")
        
        if not event_id or not event_type:
            return False, "Invalid event data - missing id or type"
        
        # ATOMIC INSERT-FIRST APPROACH
        event_log = None
        try:
            event_log = StripeEventLog(
                stripe_event_id=event_id,
                event_type=event_type,
                event_data=event_data,
                processed=False
            )
            self.db.add(event_log)
            self.db.flush()  # Force unique constraint check without commit
            
        except IntegrityError:
            # Event already exists - check if processed
            self.db.rollback()
            existing_event = self.db.query(StripeEventLog).filter(
                StripeEventLog.stripe_event_id == event_id
            ).first()
            
            if existing_event.processed:
                logger.info(f"Event {event_id} already processed successfully")
                return True, "Event already processed"
            else:
                logger.info(f"Retrying failed event {event_id}")
                event_log = existing_event
        
        # Process the event within a transaction
        try:
            with self.db.begin():
                # Update attempt count
                event_log.processing_attempts = (event_log.processing_attempts or 0) + 1
                
                # Calculate next retry time with exponential backoff
                if event_log.processing_attempts > 1:
                    backoff_seconds = min(60 * (2 ** (event_log.processing_attempts - 2)), 3600)  # Max 1 hour
                    next_retry = datetime.utcnow() + timedelta(seconds=backoff_seconds)
                    if hasattr(event_log, 'next_retry_at'):
                        event_log.next_retry_at = next_retry
                    
                    logger.info(f"Event {event_id} retry #{event_log.processing_attempts}, next retry at {next_retry}")
                
                # Process based on event type
                if event_type == "checkout.session.completed":
                    await self._handle_checkout_completed(event_data.get("data", {}).get("object"))
                elif event_type == "payment_intent.succeeded":
                    await self._handle_payment_succeeded(event_data.get("data", {}).get("object"))
                elif event_type == "payment_intent.payment_failed":
                    await self._handle_payment_failed(event_data.get("data", {}).get("object"))
                elif event_type == "invoice.payment_succeeded":
                    await self._handle_subscription_payment(event_data.get("data", {}).get("object"))
                else:
                    logger.info(f"Unhandled event type: {event_type}")
                    # Mark as processed even if unhandled to avoid retries
                
                # Mark as successfully processed
                event_log.processed = True
                event_log.processed_at = datetime.utcnow()
                event_log.error_message = None  # Clear any previous errors
                
                # Transaction commits automatically here
            
            logger.info(f"Successfully processed Stripe event {event_id} ({event_type})")
            return True, "Event processed successfully"
            
        except Exception as e:
            # Rollback any partial changes
            self.db.rollback()
            
            # Update error information
            try:
                event_log.error_message = str(e)
                if event_log.processing_attempts >= 5:
                    # Mark as dead letter after 5 attempts
                    if hasattr(event_log, 'dead_letter'):
                        event_log.dead_letter = True
                    logger.error(f"Event {event_id} marked as dead letter after 5 attempts")
                
                self.db.commit()
            except Exception as commit_error:
                logger.error(f"Failed to update error info for event {event_id}: {commit_error}")
                self.db.rollback()
            
            logger.error(f"Failed to process event {event_id}: {e}")
            
            if event_log.processing_attempts >= 5:
                return False, f"Event processing failed after 5 attempts: {str(e)}"
            
            return False, f"Event processing failed: {str(e)}"
    
    async def _handle_checkout_completed(self, session_data: Dict[str, Any]):
        """Handle successful checkout session completion."""
        user_id = session_data.get("client_reference_id") or session_data.get("metadata", {}).get("user_id")
        credits = int(session_data.get("metadata", {}).get("credits", 0))
        session_id = session_data.get("id")
        payment_intent_id = session_data.get("payment_intent")
        
        if not user_id or not credits:
            raise ValueError(f"Missing user_id or credits in checkout session: {session_id}")
        
        # Verify user exists
        user = self.db.query(User).filter(User.id == uuid.UUID(user_id)).first()
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        # Add credits to user account with idempotency protection
        await add_credits(
            user_id=uuid.UUID(user_id),
            credits=credits,
            description=f"Credit pack purchase - {credits:,} credits",
            stripe_payment_intent_id=payment_intent_id,
            idempotency_key=f"checkout_{session_id}",
            db=self.db
        )
        
        logger.info(f"Added {credits} credits to user {user_id} from checkout {session_id}")
    
    async def _handle_payment_succeeded(self, payment_intent_data: Dict[str, Any]):
        """Handle successful payment confirmation."""
        payment_intent_id = payment_intent_data.get("id")
        amount = payment_intent_data.get("amount")
        
        logger.info(f"Payment succeeded: {payment_intent_id}, amount: {amount}")
        
        # Additional payment success logic here
        # e.g., send confirmation email, update analytics, etc.
    
    async def _handle_payment_failed(self, payment_intent_data: Dict[str, Any]):
        """Handle failed payment."""
        payment_intent_id = payment_intent_data.get("id")
        failure_reason = payment_intent_data.get("last_payment_error", {}).get("message", "Unknown")
        
        logger.warning(f"Payment failed: {payment_intent_id}, reason: {failure_reason}")
        
        # Handle failed payment logic
        # e.g., notify user, log for analysis, etc.
    
    async def _handle_subscription_payment(self, invoice_data: Dict[str, Any]):
        """Handle recurring subscription payments."""
        invoice_id = invoice_data.get("id") if invoice_data else None
        customer_id = invoice_data.get("customer") if invoice_data else None
        amount_paid = invoice_data.get("amount_paid") if invoice_data else None
        
        logger.info(f"Subscription payment received: {invoice_id} for customer {customer_id}")
        
        # Add subscription credits or extend access
        # Implementation depends on subscription model
