"""action_agent

Revision ID: 004_action_agent
Revises: 003_manual_review_flag
Create Date: 2026-08-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '004_action_agent'
down_revision = '003_manual_review_flag'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'actions_agent',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('feedback_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('type_action', sa.Enum('REPONSE_CLIENT', 'TICKET_INTERNE', name='typeactionagent'), nullable=False),
        sa.Column('contenu_genere', sa.Text(), nullable=False),
        sa.Column('contenu_final', sa.Text(), nullable=True),
        sa.Column('statut', sa.Enum('EN_ATTENTE', 'VALIDEE', 'REJETEE', name='statutactionagent'), nullable=False, server_default='EN_ATTENTE'),
        sa.Column('date_creation', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('statut_envoi_whatsapp', sa.String(length=50), nullable=True),
        sa.Column('whatsapp_message_id', sa.String(length=100), nullable=True),
        sa.Column('whatsapp_erreur', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['feedback_id'], ['feedbacks.id'], ondelete='CASCADE'),
    )
    op.create_index(
        op.f('ix_actions_agent_feedback_id'), 'actions_agent', ['feedback_id']
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_actions_agent_feedback_id'), table_name='actions_agent')
    op.drop_table('actions_agent')
    sa.Enum(name='statutactionagent').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='typeactionagent').drop(op.get_bind(), checkfirst=True)
