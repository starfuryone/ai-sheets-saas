"""${message}
Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa

revision = '${up_revision}'
down_revision = ${down_revision if down_revision else None}
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
