"""
Modèles SQLAlchemy pour la mémoire conversationnelle — tables `conversations`
et `conversation_turns`, propriété EXCLUSIVE de ce service (même Base que
ActionAgent, app.db.session.Base — PAS ReadOnlyBase : ce sont des tables que
l'agent crée et écrit, pas des tables du backend principal lues en lecture
seule).

Conversation porte le CONTEXTE ACTIF (agence en discussion, période,
intention précédente, sujet actif, dernière donnée clé) — relu et mis à
jour à chaque tour par app/agent/conversation_manager.py::update_contexte_actif().
Structure attendue de `contexte_actif` :
{
  "agence_id": "uuid ou null",
  "agence_nom": "Agence Pissy ou null",
  "periode_jours": 7,
  "intention_precedente": "alertes_critiques",
  "sujet_actif": "panne réseau ou null",
  "derniere_donnee_cle": "tout ce qui permettrait de répondre à 'pourquoi ?'"
}

ConversationTurn est l'historique immuable des échanges (un tour = une
question + sa réponse), utilisé pour reconstruire l'historique de messages
envoyé au LLM (voir conversation_manager.build_messages_history()).
`donnees_resumees` est une version CONDENSÉE des données ayant servi à la
réponse (jamais la totalité) — voir conversation_manager._resumer_donnees().
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Pas de FK vers agences.id (table du backend principal, hors du Base de
    # ce service) — cohérent avec le traitement de feedback_id sur
    # ActionAgent, mais ici volontairement sans contrainte FK PostgreSQL non
    # plus : une conversation peut exister sans agence de référence (question
    # tous-agences) et agence_id peut changer de sens au fil des tours.
    agence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    utilisateur_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="FK logique vers utilisateurs.id — contrainte DB présente "
                "mais ForeignKey ORM retiré (utilisateurs est sur ReadOnlyBase, "
                "pas sur Base — même pattern que agence_id).",
    )
    date_creation: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    derniere_activite: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    contexte_actif: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<Conversation {self.id} agence={self.agence_id}>"


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tour_numero: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    intention: Mapped[str] = mapped_column(String(50), nullable=False)
    reponse: Mapped[str] = mapped_column(Text, nullable=False)
    donnees_resumees: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    date_creation: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<ConversationTurn {self.tour_numero} "
            f"conversation={self.conversation_id} intention={self.intention}>"
        )
