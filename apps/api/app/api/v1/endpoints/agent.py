"""
Endpoints Agent IA — validation humaine des brouillons d'action (ActionAgent).
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_cx_or_agency_manager, get_db
from app.models.action_agent import ActionAgent
from app.models.enums import StatutActionAgent, TypeActionAgent
from app.models.utilisateur import Utilisateur
from app.services.ai.agent import action_service, qa_service

router = APIRouter()


class ActionAgentResponse(BaseModel):
    id: UUID
    feedback_id: UUID
    type_action: TypeActionAgent
    contenu_genere: str
    contenu_final: Optional[str] = None
    statut: StatutActionAgent
    date_creation: datetime
    statut_envoi_whatsapp: Optional[str] = None
    whatsapp_message_id: Optional[str] = None
    whatsapp_erreur: Optional[str] = None

    model_config = {"from_attributes": True}


class ValiderActionRequest(BaseModel):
    contenu_final: Optional[str] = None


class AskRequest(BaseModel):
    question: str
    agence_id: Optional[UUID] = None
    jours: int = 7


class AskResponse(BaseModel):
    intention: str
    reponse: str
    donnees: Any = None


class GenererBrouillonRequest(BaseModel):
    feedback_id: UUID
    type_action: TypeActionAgent


@router.post("/ask", response_model=AskResponse)
def ask(
    data: AskRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_cx_or_agency_manager),
):
    """
    Répond à une question en langage naturel d'un manager sur les
    feedbacks (alertes, statistiques, problèmes récurrents, tendances...).
    Voir app.services.ai.agent.qa_service pour la liste des intentions
    reconnues (intentions.yaml).
    """
    return qa_service.repondre_question(
        db, data.question, agence_id=data.agence_id, jours=data.jours
    )


@router.post("/actions/brouillon", response_model=ActionAgentResponse)
def generer_brouillon(
    data: GenererBrouillonRequest,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_cx_or_agency_manager),
):
    """
    Génère manuellement un brouillon d'action pour un feedback déjà
    analysé (en plus de la génération automatique déclenchée par
    declencher_alerte_si_critique pour les feedbacks critiques).
    """
    try:
        return action_service.generer_brouillon(db, data.feedback_id, data.type_action)
    except action_service.FeedbackNonAnalyseError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/actions", response_model=list[ActionAgentResponse])
def lister_actions_en_attente(
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_cx_or_agency_manager),
):
    """Liste les brouillons d'action en attente de validation humaine."""
    return (
        db.query(ActionAgent)
        .filter(ActionAgent.statut == StatutActionAgent.EN_ATTENTE)
        .order_by(ActionAgent.date_creation.desc())
        .all()
    )


@router.post("/actions/{action_id}/rejeter", response_model=ActionAgentResponse)
def rejeter_action(
    action_id: UUID,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_cx_or_agency_manager),
):
    """Rejette un brouillon d'action (statut -> REJETEE), sans envoi WhatsApp."""
    try:
        return action_service.rejeter_action(db, action_id)
    except action_service.ActionInconnueError:
        raise HTTPException(status_code=404, detail="Action introuvable")


@router.post("/actions/{action_id}/valider", response_model=ActionAgentResponse)
def valider_action(
    action_id: UUID,
    data: ValiderActionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(get_cx_or_agency_manager),
):
    """
    Valide un brouillon d'action (statut -> VALIDEE). La réponse HTTP
    confirme la validation immédiatement, sans attendre l'appel réseau à
    l'API Meta : la tentative d'envoi WhatsApp (si REPONSE_CLIENT et
    numéro de contact disponible) s'exécute en tâche de fond et met à jour
    statut_envoi_whatsapp / whatsapp_message_id / whatsapp_erreur une fois
    terminée.
    """
    try:
        action = action_service.valider_action(db, action_id, contenu_final=data.contenu_final)
    except action_service.ActionInconnueError:
        raise HTTPException(status_code=404, detail="Action introuvable")

    background_tasks.add_task(action_service.tenter_envoi_whatsapp_action, action.id)
    return action
