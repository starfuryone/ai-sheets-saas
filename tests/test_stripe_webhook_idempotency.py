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


class TestStripeWebhookIdempotency:
    """Test Stripe webhook idempotency protection."""
    
    def create_webhook_signature(self, payload: str, secret: str = "whsec_test_secret") -> str:
        """Create valid Stripe webhook signature."""
        timestamp = str(int(time.time()))
        signed_payload = f"{timestamp}.{payload}"
        signature = hmac.new(
            secret.encode('utf-8'),
            signed_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"t={timestamp},v1={signature}"
    
    @pytest.mark.asyncio
    async def test_duplicate_event_handling(self, db_session: Session, test_user):
        """Test that duplicate events are handled correctly."""
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

    @pytest.mark.asyncio
    async def test_failed_event_retry_logic(self, db_session: Session, test_user):
        """Test retry logic for failed events."""
        event_data = {
            "id": "evt_test_retry",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_retry",
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
            StripeEventLog.stripe_event_id == "evt_test_retry"
        ).first()
        assert event is not None
        assert not event.processed
        assert event.processing_attempts == 1
        assert event.error_message == "Test error"
        
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

    def test_webhook_endpoint_integration(self, test_client: TestClient, db_session: Session, test_user):
        """Test complete webhook endpoint with signature verification."""
        webhook_payload = {
            "id": "evt_test_webhook_123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "client_reference_id": str(test_user.id),
                    "payment_intent": "pi_test_123",
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
        
        # Verify event was logged
        event_log = db_session.query(StripeEventLog).filter(
            StripeEventLog.stripe_event_id == "evt_test_webhook_123"
        ).first()
        assert event_log is not None
        assert event_log.processed is True
        assert event_log.event_type == "checkout.session.completed"

    def test_webhook_signature_validation(self, test_client: TestClient):
        """Test webhook signature verification."""
        payload = json.dumps({"id": "evt_test", "type": "test.event"})
        
        # Test missing signature
        response = test_client.post("/stripe/webhook", content=payload)
        assert response.status_code == 400
        assert "Missing Stripe signature" in response.json()["detail"]
        
        # Test invalid signature
        response = test_client.post(
            "/stripe/webhook",
            content=payload,
            headers={"stripe-signature": "invalid_signature"}
        )
        assert response.status_code == 400
        assert "Invalid signature" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_max_retry_limit(self, db_session: Session, test_user):
        """Test that events fail after maximum retry attempts."""
        event_data = {
            "id": "evt_test_max_retries",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_max_retries",
                    "client_reference_id": str(test_user.id),
                    "metadata": {"credits": "25"}
                }
            }
        }
        
        processor = StripeEventProcessor(db_session)
        
        # Simulate failures for all attempts
        with patch('app.services.credits.add_credits', side_effect=Exception("Persistent error")):
            for attempt in range(5):
                success, message = await processor.process_event(event_data)
                assert not success
                
                # Verify attempt count
                event = db_session.query(StripeEventLog).filter(
                    StripeEventLog.stripe_event_id == "evt_test_max_retries"
                ).first()
                assert event.processing_attempts == attempt + 1
            
            # Final attempt should indicate max retries exceeded
            assert "after 5 attempts" in message

    def test_event_status_endpoint(self, test_client: TestClient, db_session: Session):
        """Test the event status lookup endpoint."""
        # Create a test event log
        event_log = StripeEventLog(
            stripe_event_id="evt_test_status",
            event_type="payment_intent.succeeded",
            processed=True,
            processing_attempts=1
        )
        db_session.add(event_log)
        db_session.commit()
        
        # Test successful lookup
        response = test_client.get("/stripe/events/evt_test_status/status")
        assert response.status_code == 200
        
        data = response.json()
        assert data["event_id"] == "evt_test_status"
        assert data["event_type"] == "payment_intent.succeeded"
        assert data["processed"] is True
        assert data["processing_attempts"] == 1
        
        # Test not found
        response = test_client.get("/stripe/events/nonexistent_event/status")
        assert response.status_code == 404
