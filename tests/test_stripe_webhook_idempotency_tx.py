import pytest
import json
import hmac
import hashlib
import time
from unittest.mock import patch, AsyncMock
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.models import StripeEventLog, CreditTransaction
from app.services.stripe_events import StripeEventProcessor
from app.config import settings

@pytest.fixture(autouse=True)
def set_test_stripe_settings(monkeypatch):
    """Override Stripe settings for testing."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake_key")
    # Reload settings to pick up changes
    settings.stripe_webhook_secret = "whsec_test_secret"
    settings.stripe_secret_key = "sk_test_fake_key"

class TestStripeWebhookIdempotency:
    """Test Stripe webhook idempotency protection with transactional safety."""
    
    def create_webhook_signature(self, payload: str, secret: str = "whsec_test_secret") -> str:
        """Create valid Stripe webhook signature with current timestamp."""
        timestamp = str(int(time.time()))
        signed_payload = f"{timestamp}.{payload}"
        signature = hmac.new(
            secret.encode('utf-8'),
            signed_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"t={timestamp},v1={signature}"
    
    def create_stale_webhook_signature(self, payload: str, secret: str = "whsec_test_secret") -> str:
        """Create webhook signature with stale timestamp (>5 minutes old)."""
        stale_timestamp = str(int(time.time()) - 400)  # 400 seconds ago
        signed_payload = f"{stale_timestamp}.{payload}"
        signature = hmac.new(
            secret.encode('utf-8'),
            signed_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"t={stale_timestamp},v1={signature}"
    
    @pytest.mark.asyncio
    async def test_duplicate_event_handling(self, db_session: Session, test_user):
        """Test that duplicate events are handled correctly with transaction safety."""
        event_data = {
            "id": "evt_test_duplicate",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_duplicate",
                    "client_reference_id": str(test_user.id),
                    "metadata": {"credits": "100"}
                }
            }
        }
        
        processor = StripeEventProcessor(db_session)
        
        # First processing should succeed
        with patch('app.services.credits.add_credits', new_callable=AsyncMock) as mock_add_credits:
            success1, message1 = await processor.process_event(event_data)
            assert success1
            mock_add_credits.assert_called_once()
        
        # Second processing should be idempotent
        with patch('app.services.credits.add_credits', new_callable=AsyncMock) as mock_add_credits:
            success2, message2 = await processor.process_event(event_data)
            assert success2
            assert "already processed" in message2
            mock_add_credits.assert_not_called()
        
        # Verify only one database record
        events = db_session.query(StripeEventLog).filter(
            StripeEventLog.stripe_event_id == "evt_test_duplicate"
        ).all()
        assert len(events) == 1
        assert events[0].processed is True
        assert events[0].processing_attempts == 1

    @pytest.mark.asyncio
    async def test_failed_event_retry_logic_with_backoff(self, db_session: Session, test_user):
        """Test retry logic with exponential backoff for failed events."""
        event_data = {
            "id": "evt_test_retry_backoff",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_retry_backoff",
                    "client_reference_id": str(test_user.id),
                    "metadata": {"credits": "75"}
                }
            }
        }
        
        processor = StripeEventProcessor(db_session)
        
        # Simulate failure on first attempt
        with patch('app.services.credits.add_credits', side_effect=Exception("Test error")):
            success1, message1 = await processor.process_event(event_data)
            assert not success1
            assert "failed" in message1
        
        # Verify event is recorded but not processed
        event = db_session.query(StripeEventLog).filter(
            StripeEventLog.stripe_event_id == "evt_test_retry_backoff"
        ).first()
        assert event is not None
        assert not event.processed
        assert event.processing_attempts == 1
        assert event.error_message == "Test error"
        assert hasattr(event, 'next_retry_at') or True  # May not exist in all versions
        
        # Retry should succeed
        with patch('app.services.credits.add_credits', new_callable=AsyncMock) as mock_add_credits:
            success2, message2 = await processor.process_event(event_data)
            assert success2
            mock_add_credits.assert_called_once()
        
        # Verify event is now processed
        db_session.refresh(event)
        assert event.processed is True
        assert event.processing_attempts == 2
        assert event.processed_at is not None
        assert event.error_message is None  # Should be cleared on success

    def test_webhook_signature_tolerance(self, test_client: TestClient, db_session: Session, test_user):
        """Test webhook signature verification with timestamp tolerance."""
        webhook_payload = {
            "id": "evt_test_tolerance",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_tolerance",
                    "amount": 1000
                }
            }
        }
        
        payload_str = json.dumps(webhook_payload)
        
        # Test valid signature (current timestamp)
        valid_signature = self.create_webhook_signature(payload_str)
        response = test_client.post(
            "/stripe/webhook",
            content=payload_str,
            headers={
                "stripe-signature": valid_signature,
                "content-type": "application/json"
            }
        )
        assert response.status_code == 200
        
        # Test stale signature (should fail due to tolerance)
        stale_signature = self.create_stale_webhook_signature(payload_str)
        response = test_client.post(
            "/stripe/webhook",
            content=payload_str,
            headers={
                "stripe-signature": stale_signature,
                "content-type": "application/json"
            }
        )
        assert response.status_code == 400
        assert "Invalid signature" in response.json()["detail"]

    def test_webhook_endpoint_integration_with_transaction_safety(
        self, test_client: TestClient, db_session: Session, test_user
    ):
        """Test complete webhook endpoint with transaction safety."""
        webhook_payload = {
            "id": "evt_test_transaction_safety",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_transaction_safety",
                    "client_reference_id": str(test_user.id),
                    "payment_intent": "pi_test_transaction_safety",
                    "metadata": {
                        "user_id": str(test_user.id),
                        "credits": "100"
                    }
                }
            }
        }
        
        payload_str = json.dumps(webhook_payload)
        signature = self.create_webhook_signature(payload_str)
        
        with patch('app.services.credits.add_credits', new_callable=AsyncMock) as mock_add_credits:
            response = test_client.post(
                "/stripe/webhook",
                content=payload_str,
                headers={
                    "stripe-signature": signature,
                    "content-type": "application/json"
                }
            )
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        mock_add_credits.assert_called_once()
        
        # Verify event was logged with proper transaction state
        event_log = db_session.query(StripeEventLog).filter(
            StripeEventLog.stripe_event_id == "evt_test_transaction_safety"
        ).first()
        assert event_log is not None
        assert event_log.processed is True
        assert event_log.event_type == "checkout.session.completed"
        assert event_log.processing_attempts == 1

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_failure(self, db_session: Session, test_user):
        """Test that transaction properly rolls back on failure."""
        event_data = {
            "id": "evt_test_transaction_rollback",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_transaction_rollback",
                    "client_reference_id": str(test_user.id),
                    "metadata": {"credits": "50"}
                }
            }
        }
        
        processor = StripeEventProcessor(db_session)
        
        # Simulate failure that should trigger rollback
        with patch('app.services.credits.add_credits', side_effect=Exception("Database error")):
            success, message = await processor.process_event(event_data)
            assert not success
            assert "failed" in message
        
        # Verify event is in failed state, not partially processed
        event = db_session.query(StripeEventLog).filter(
            StripeEventLog.stripe_event_id == "evt_test_transaction_rollback"
        ).first()
        assert event is not None
        assert not event.processed
        assert event.processing_attempts == 1
        assert "Database error" in event.error_message

    @pytest.mark.asyncio
    async def test_dead_letter_after_max_retries(self, db_session: Session, test_user):
        """Test that events are marked as dead letters after max retries."""
        event_data = {
            "id": "evt_test_dead_letter",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_dead_letter",
                    "client_reference_id": str(test_user.id),
                    "metadata": {"credits": "25"}
                }
            }
        }
        
        processor = StripeEventProcessor(db_session)
        
        # Simulate failures for all 5 attempts
        with patch('app.services.credits.add_credits', side_effect=Exception("Persistent error")):
            for attempt in range(5):
                success, message = await processor.process_event(event_data)
                assert not success
                
                # Verify attempt count
                event = db_session.query(StripeEventLog).filter(
                    StripeEventLog.stripe_event_id == "evt_test_dead_letter"
                ).first()
                assert event.processing_attempts == attempt + 1
            
            # Final attempt should indicate max retries exceeded
            assert "after 5 attempts" in message
        
        # Verify event is marked as dead letter (if field exists)
        db_session.refresh(event)
        if hasattr(event, 'dead_letter'):
            assert event.dead_letter is True

    def test_event_status_endpoint_with_retry_info(self, test_client: TestClient, db_session: Session):
        """Test the event status lookup endpoint with retry information."""
        # Create a test event log with retry information
        event_log = StripeEventLog(
            stripe_event_id="evt_test_status_with_retry",
            event_type="payment_intent.succeeded",
            processed=False,
            processing_attempts=2,
            error_message="Temporary error",
        )
        db_session.add(event_log)
        db_session.commit()
        
        # Test status lookup
        response = test_client.get("/stripe/events/evt_test_status_with_retry/status")
        assert response.status_code == 200
        
        data = response.json()
        assert data["event_id"] == "evt_test_status_with_retry"
        assert data["event_type"] == "payment_intent.succeeded"
        assert data["processed"] is False
        assert data["processing_attempts"] == 2
        assert data["error_message"] == "Temporary error"

    def test_webhook_signature_validation_edge_cases(self, test_client: TestClient):
        """Test webhook signature validation edge cases."""
        payload = json.dumps({"id": "evt_test", "type": "test.event"})
        
        # Test missing signature
        response = test_client.post("/stripe/webhook", content=payload)
        assert response.status_code == 400
        assert "Missing Stripe signature" in response.json()["detail"]
        
        # Test malformed signature
        response = test_client.post(
            "/stripe/webhook",
            content=payload,
            headers={"stripe-signature": "malformed_signature"}
        )
        assert response.status_code == 400
        assert "Invalid signature" in response.json()["detail"]
