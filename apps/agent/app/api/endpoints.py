"""
Endpoints de l'agent IA — 5 endpoints portés du prototype + 1 webhook.
"""
import hmac
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.agent import action_service, qa_service
from app.api.deps import require_agent_access
from app.config.settings import settings
from app.db.session import SessionLocal, get_db
from app.models.action_agent import ActionAgent
from app.models.enums import StatutActionAgent, CriticiteType
from app.models.readonly import Utilisateur
from app.schemas.models import (
    AskRequest,
    AskResponse,
    BrouillonRequest,
    ActionAgentResponse,
    ValiderRequest,
    WebhookAnalyseComplete,
)

logger = logging.getLogger(__name__)

agent_router = APIRouter(prefix="/agent", tags=["Agent IA"])
webhook_router = APIRouter(prefix="/webhook", tags=["Webhook"])


@agent_router.post("/ask", response_model=AskResponse)
def ask(
    payload: AskRequest,
    db: Session = Depends(get_db),
    _current_user: Utilisateur = Depends(require_agent_access),
):
    """Q&A conversationnel pour les managers."""
    resultat = qa_service.repondre_question(
        db, payload.question, agence_id=payload.agence_id, jours=payload.jours
    )
    return AskResponse(**resultat)


@agent_router.post("/actions/brouillon", response_model=ActionAgentResponse)
def generer_brouillon(
    payload: BrouillonRequest,
    db: Session = Depends(get_db),
    _current_user: Utilisateur = Depends(require_agent_access),
):
    """Génère manuellement un brouillon d'action pour un feedback déjà analysé."""
    try:
        action = action_service.generer_brouillon(db, payload.feedback_id, payload.type_action)
    except action_service.FeedbackNonAnalyseError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ActionAgentResponse.model_validate(action)


@agent_router.get("/actions", response_model=list[ActionAgentResponse])
def lister_actions_en_attente(
    db: Session = Depends(get_db),
    _current_user: Utilisateur = Depends(require_agent_access),
):
    """Liste des brouillons en attente de validation."""
    actions = (
        db.query(ActionAgent)
        .filter(ActionAgent.statut == StatutActionAgent.EN_ATTENTE)
        .order_by(ActionAgent.date_creation.desc())
        .all()
    )
    return [ActionAgentResponse.model_validate(a) for a in actions]


@agent_router.post("/actions/{action_id}/valider", response_model=ActionAgentResponse)
def valider(
    action_id: uuid.UUID,
    payload: ValiderRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Utilisateur = Depends(require_agent_access),
):
    """
    Valide un brouillon. La réponse HTTP confirme la validation
    immédiatement ; l'envoi WhatsApp éventuel (si REPONSE_CLIENT + numéro
    de contact disponible) est tenté en tâche de fond.
    """
    try:
        action = action_service.valider_action(
            db, action_id, valide_par_id=current_user.id, contenu_final=payload.contenu_final
        )
    except action_service.ActionInconnueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    background_tasks.add_task(action_service.envoyer_whatsapp_si_applicable, action_id)
    return ActionAgentResponse.model_validate(action)


@agent_router.post("/actions/{action_id}/rejeter", response_model=ActionAgentResponse)
def rejeter(
    action_id: uuid.UUID,
    db: Session = Depends(get_db),
    _current_user: Utilisateur = Depends(require_agent_access),
):
    """Rejette un brouillon d'action."""
    try:
        action = action_service.rejeter_action(db, action_id)
    except action_service.ActionInconnueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ActionAgentResponse.model_validate(action)


def _verifier_secret_webhook(x_webhook_secret: str | None) -> None:
    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, settings.WEBHOOK_SECRET):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Secret webhook invalide")


def _declencher_alerte_en_tache_de_fond(feedback_id: uuid.UUID) -> None:
    """Ouvre sa propre session DB — exécutée après la réponse HTTP du webhook."""
    db = SessionLocal()
    try:
        action = action_service.declencher_alerte_si_critique(db, feedback_id)
        if action is not None:
            logger.info(f"Alerte déclenchée — brouillon {action.id} pour feedback {feedback_id}")
    except Exception:
        logger.exception(f"Échec du déclenchement d'alerte pour feedback {feedback_id}")
    finally:
        db.close()


@webhook_router.post("/analyse-complete", status_code=status.HTTP_202_ACCEPTED)
def webhook_analyse_complete(
    payload: WebhookAnalyseComplete,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str | None = Header(default=None),
):
    """
    Appelé par le backend principal juste après la création d'une AnalyseIA.
    Protégé par un secret partagé (header X-Webhook-Secret), PAS par JWT —
    c'est un appel service-à-service, pas un appel utilisateur.
    """
    _verifier_secret_webhook(x_webhook_secret)

    if payload.criticite.lower() in {CriticiteType.ELEVEE.value, CriticiteType.CRITIQUE.value}:
        background_tasks.add_task(_declencher_alerte_en_tache_de_fond, payload.feedback_id)

    return {"status": "accepted"}
