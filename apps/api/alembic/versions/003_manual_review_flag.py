"""add_necessite_verification_to_analyses_ia

Revision ID: 003_manual_review_flag
Revises: 002_organisation_fields
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa

revision = '003_manual_review_flag'
down_revision = '002_organisation_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'analyses_ia',
        sa.Column('necessite_verification', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('analyses_ia', 'necessite_verification')
