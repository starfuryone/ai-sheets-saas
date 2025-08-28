import pytest
import uuid

from sqlalchemy.orm import Session

from app.models import StripeEventLog, User
from app.services.stripe_events import StripeEventProcessor

pytestmark = pytest.mark.asyncio

class TestStripeIdempotency:
    """Test Stripe webhook idempotency protection."""

    async def test_duplicate_event_handling(self, db_session: Session):
        """Test that duplicate events are handled correctly."""
        # Create a user to receive credits
        user = User(email="idempotency@example.com")
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        event_data = {
            "id": "evt_test_duplicate",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "client_reference_id": str(user.id),
                    "metadata": {"credits": "100"}
                }
            }
        }

        processor = StripeEventProcessor(db_session)

        # First processing should succeed
        success1, message1 = await processor.process_event(event_data)
        assert success1, message1

        # Second processing should be idempotent
        success2, message2 = await processor.process_event(event_data)
        assert success2, message2
        assert "already processed" in message2.lower() or "successfully" in message2.lower()

        # Verify only one database record for the event
        events = db_session.query(StripeEventLog).filter(
            StripeEventLog.stripe_event_id == "evt_test_duplicate"
        ).all()
        assert len(events) == 1
        assert events[0].processed is True
