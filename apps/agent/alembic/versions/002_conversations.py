"""ajout conversations et conversation_turns (memoire conversationnelle)

Revision ID: 002_conversations
Revises: 001_action_agent
Create Date: 2026-09-05 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002_conversations"
down_revision: Union[str, None] = "001_action_agent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("agence_id", sa.UUID(), nullable=True),
        sa.Column("utilisateur_id", sa.UUID(), nullable=True),
        sa.Column("date_creation", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("derniere_activite", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("contexte_actif", sa.JSON(), nullable=True),
        # Pas de FK vers agences.id (table du backend principal, hors de cet
        # Alembic) — voir commentaire dans app/models/conversation.py.
        sa.ForeignKeyConstraint(["utilisateur_id"], ["utilisateurs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("tour_numero", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("intention", sa.String(length=50), nullable=False),
        sa.Column("reponse", sa.Text(), nullable=False),
        sa.Column("donnees_resumees", sa.JSON(), nullable=True),
        sa.Column("date_creation", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_conversation_turns_conversation_id"), "conversation_turns", ["conversation_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_conversation_turns_conversation_id"), table_name="conversation_turns")
    op.drop_table("conversation_turns")
    op.drop_table("conversations")
