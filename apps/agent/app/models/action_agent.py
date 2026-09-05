"""
Modèle ActionAgent — table `actions_agent`, propriété EXCLUSIVE de ce service.
Le backend principal ne connaît pas cette table ; elle vit sur le Base
Alembic de ce projet (app.db.session.Base), séparé du ReadOnlyBase des
tables du backend principal (voir app/models/readonly.py).

Colonnes conformes au guide d'intégration fourni par Lionel (Chief AI Officer).
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.enums import TypeActionAgent, StatutActionAgent


class ActionAgent(Base):
    __tablename__ = "actions_agent"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # FK logique vers feedbacks.id (table du backend principal, hors de ce
    # Base — la contrainte FK existe bien au niveau PostgreSQL, la table
    # cible n'a juste pas de modèle ORM ici).
    feedback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feedbacks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type_action: Mapped[TypeActionAgent] = mapped_column(Enum(TypeActionAgent), nullable=False)
    contenu_genere: Mapped[str] = mapped_column(Text, nullable=False)
    contenu_final: Mapped[str | None] = mapped_column(Text, nullable=True)
    statut: Mapped[StatutActionAgent] = mapped_column(
        Enum(StatutActionAgent), nullable=False, default=StatutActionAgent.EN_ATTENTE, index=True
    )
    valide_par_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True
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
