"""
Schémas Pydantic — requêtes/réponses des endpoints de l'agent.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TypeActionAgent, StatutActionAgent


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    # ATTENTION : doit être un UUID valide ou ABSENT du JSON, jamais une
    # chaîne vide "" (voir GUIDE_INTEGRATION.md) — Pydantic rejette "" pour
    # un champ Optional[UUID], ce qui est le comportement souhaité ici.
    agence_id: Optional[UUID] = None
    jours: int = 7


class AskResponse(BaseModel):
    intention: str
    reponse: str
    donnees: Any = None


class BrouillonRequest(BaseModel):
    feedback_id: UUID
    type_action: TypeActionAgent


class ValiderRequest(BaseModel):
    contenu_final: Optional[str] = None


class ActionAgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    feedback_id: UUID
    type_action: TypeActionAgent
    contenu_genere: str
    contenu_final: Optional[str] = None
    statut: StatutActionAgent
    valide_par_id: Optional[UUID] = None
    valide_le: Optional[datetime] = None
    date_creation: datetime
    statut_envoi_whatsapp: Optional[str] = None
    whatsapp_message_id: Optional[str] = None
    whatsapp_erreur: Optional[str] = None


class WebhookAnalyseComplete(BaseModel):
    feedback_id: UUID
    criticite: str
