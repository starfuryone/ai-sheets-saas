"""Initial schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('name', sa.String(255)),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
    )

    # Create idempotency log table
    op.create_table(
        'idempotency_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('idempotency_key', sa.String(255), unique=True, nullable=False),
        sa.Column('request_hash', sa.String(255)),
        sa.Column('response_data', JSONB),
        sa.Column('status_code', sa.Integer),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
    )

    # Create indexes
    op.create_index('ix_credit_transactions_user_created', 'credit_transactions', ['user_id', 'created_at'])
    op.create_index('ix_credit_transactions_idempotency', 'credit_transactions', ['idempotency_key'])
    op.create_index('ix_usage_events_user_created', 'usage_events', ['user_id', 'created_at'])
    op.create_index('ix_usage_events_function', 'usage_events', ['function_name'])
    op.create_index('ix_usage_events_idempotency', 'usage_events', ['idempotency_key'])
    op.create_index('ix_idempotency_key', 'idempotency_log', ['idempotency_key'])

def downgrade() -> None:
    pass
