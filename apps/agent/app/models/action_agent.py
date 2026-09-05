"""
Modèle ActionAgent — table `actions_agent`, propriété EXCLUSIVE de ce service.
Le backend principal ne connaît pas cette table ; elle vit sur le Base
Alembic de ce projet (app.db.session.Base), séparé du ReadOnlyBase des
tables du backend principal (voir app/models/readonly.py).

Colonnes conformes au guide d'intégration fourni par Lionel (Chief AI Officer).
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.enums import TypeActionAgent, StatutActionAgent


class ActionAgent(Base):
    __tablename__ = "actions_agent"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # FK logique vers feedbacks.id — contrainte DB déjà présente en base
    # (voir alembic/versions/001_action_agent.py), mais ForeignKey ORM
    # retiré : feedbacks est sur ReadOnlyBase, pas sur Base (celui-ci), donc
    # SQLAlchemy ne peut pas résoudre la table pour l'ordre de flush et lève
    # NoReferencedTableError au premier INSERT (confirmé empiriquement —
    # même pattern que Conversation.utilisateur_id, voir
    # app/models/conversation.py).
    feedback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    type_action: Mapped[TypeActionAgent] = mapped_column(Enum(TypeActionAgent), nullable=False)
    contenu_genere: Mapped[str] = mapped_column(Text, nullable=False)
    contenu_final: Mapped[str | None] = mapped_column(Text, nullable=True)
    statut: Mapped[StatutActionAgent] = mapped_column(
        Enum(StatutActionAgent), nullable=False, default=StatutActionAgent.EN_ATTENTE, index=True
    )
    # Même raison que feedback_id ci-dessus : utilisateurs est sur
    # ReadOnlyBase, pas sur Base — ForeignKey ORM retiré, contrainte DB
    # déjà présente en base.
    valide_par_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    valide_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    date_creation: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Renseignées par la tâche de fond d'envoi WhatsApp (jamais synchrones)
    statut_envoi_whatsapp: Mapped[str | None] = mapped_column(String(50), nullable=True)
    whatsapp_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    whatsapp_erreur: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<ActionAgent {self.type_action} feedback={self.feedback_id} statut={self.statut}>"
