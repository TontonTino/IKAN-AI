"""init actions_agent

Revision ID: 001_action_agent
Revises:
Create Date: 2026-08-28 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001_action_agent"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "actions_agent",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("feedback_id", sa.UUID(), nullable=False),
        sa.Column(
            "type_action",
            sa.Enum("REPONSE_CLIENT", "TICKET_INTERNE", name="typeactionagent"),
            nullable=False,
        ),
        sa.Column("contenu_genere", sa.Text(), nullable=False),
        sa.Column("contenu_final", sa.Text(), nullable=True),
        sa.Column(
            "statut",
            sa.Enum("EN_ATTENTE", "VALIDEE", "REJETEE", name="statutactionagent"),
            nullable=False,
        ),
        sa.Column("valide_par_id", sa.UUID(), nullable=True),
        sa.Column("valide_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_creation", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("statut_envoi_whatsapp", sa.String(length=50), nullable=True),
        sa.Column("whatsapp_message_id", sa.String(length=200), nullable=True),
        sa.Column("whatsapp_erreur", sa.String(length=500), nullable=True),
        # Contraintes FK au niveau PostgreSQL vers les tables du backend
        # principal (feedbacks, utilisateurs) — ces tables ne sont pas
        # gérées par cet Alembic, elles doivent déjà exister en base
        # (migrations de apps/api appliquées en premier).
        sa.ForeignKeyConstraint(["feedback_id"], ["feedbacks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["valide_par_id"], ["utilisateurs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_actions_agent_feedback_id"), "actions_agent", ["feedback_id"])
    op.create_index(op.f("ix_actions_agent_statut"), "actions_agent", ["statut"])


def downgrade() -> None:
    op.drop_index(op.f("ix_actions_agent_statut"), table_name="actions_agent")
    op.drop_index(op.f("ix_actions_agent_feedback_id"), table_name="actions_agent")
    op.drop_table("actions_agent")
    op.execute("DROP TYPE IF EXISTS typeactionagent")
    op.execute("DROP TYPE IF EXISTS statutactionagent")
