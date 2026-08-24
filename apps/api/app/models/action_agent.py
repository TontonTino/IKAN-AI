"""
Modèle ActionAgent — brouillon d'action généré par l'agent IA (réponse client
ou ticket interne) pour un feedback critique, en attente de validation humaine.

Distinct de Recommandation (BF-17, templates statiques internes à l'Agency
Manager) : ActionAgent porte un contenu généré par LLM (Mistral), destiné
potentiellement à être envoyé AU CLIENT par WhatsApp après validation.
Aucune action n'est envoyée automatiquement — voir app/services/ai/agent/action_service.py.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import TypeActionAgent, StatutActionAgent


class ActionAgent(Base):
    __tablename__ = "actions_agent"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    feedback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feedbacks.id", ondelete="CASCADE"), nullable=False
    )
    type_action: Mapped[TypeActionAgent] = mapped_column(Enum(TypeActionAgent), nullable=False)
    contenu_genere: Mapped[str] = mapped_column(Text, nullable=False)
    contenu_final: Mapped[str | None] = mapped_column(Text, nullable=True)
    statut: Mapped[StatutActionAgent] = mapped_column(
        Enum(StatutActionAgent), nullable=False, default=StatutActionAgent.EN_ATTENTE
    )
    date_creation: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Résultat de la tentative d'envoi WhatsApp (renseigné en tâche de fond
    # après validation — voir POST /agent/actions/{id}/valider).
    statut_envoi_whatsapp: Mapped[str | None] = mapped_column(String(50), nullable=True)
    whatsapp_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    whatsapp_erreur: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relations
    feedback: Mapped["Feedback"] = relationship("Feedback", back_populates="actions_agent")

    def __repr__(self) -> str:
        return f"<ActionAgent {self.type_action} statut={self.statut} feedback={self.feedback_id}>"
