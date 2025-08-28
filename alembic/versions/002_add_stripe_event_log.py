"""Add stripe event log table for webhook idempotency

Revision ID: 002_add_stripe_event_log
Revises: 001_initial_schema
Create Date: 2025-08-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = '002_add_stripe_event_log'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Ensure required extension for gen_random_uuid()
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    
    # Create stripe event log table for idempotency
    op.create_table(
        'stripe_event_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('stripe_event_id', sa.String(255), unique=True, nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('event_data', JSONB),
        sa.Column('processed', sa.Boolean, server_default=sa.text('false'), nullable=False),
        sa.Column('processing_attempts', sa.Integer, server_default=sa.text('0'), nullable=False),
        sa.Column('error_message', sa.Text),
        sa.Column('processed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('next_retry_at', sa.DateTime(timezone=True)),
        sa.Column('dead_letter', sa.Boolean, server_default=sa.text('false'), nullable=False),
        
        # Add CHECK constraint for processing_attempts
        sa.CheckConstraint('processing_attempts >= 0', name='ck_processing_attempts_non_negative')
    )
    
    # Create indexes (stripe_event_id is already unique via column constraint)
    op.create_index('ix_stripe_event_processed', 'stripe_event_log', ['processed', 'created_at'])
    op.create_index('ix_stripe_event_type', 'stripe_event_log', ['event_type'])
    op.create_index('ix_stripe_event_attempts', 'stripe_event_log', ['processing_attempts'])
    op.create_index('ix_stripe_event_retry', 'stripe_event_log', ['next_retry_at'])
    op.create_index('ix_stripe_event_dead_letter', 'stripe_event_log', ['dead_letter'])
    # JSONB gin index for querying event data
    op.create_index('ix_stripe_event_data_gin', 'stripe_event_log', ['event_data'], postgresql_using='gin')

def downgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_stripe_event_data_gin', 'stripe_event_log')
    op.drop_index('ix_stripe_event_dead_letter', 'stripe_event_log')
    op.drop_index('ix_stripe_event_retry', 'stripe_event_log')
    op.drop_index('ix_stripe_event_attempts', 'stripe_event_log')
    op.drop_index('ix_stripe_event_type', 'stripe_event_log')
    op.drop_index('ix_stripe_event_processed', 'stripe_event_log')
    
    # Drop table (this automatically drops the unique constraint and check constraint)
    op.drop_table('stripe_event_log')
