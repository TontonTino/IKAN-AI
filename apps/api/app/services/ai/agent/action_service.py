"""
Service de génération et de gestion des brouillons d'action (ActionAgent).

Porté depuis le prototype (Agent IA/app/agent/action_service.py).

Règles architecturales appliquées ici :
  - Tout brouillon créé a le statut EN_ATTENTE. valider_action() se
    contente de changer le statut ; la tentative d'envoi WhatsApp est
    déclenchée séparément, en tâche de fond, par
    tenter_envoi_whatsapp_action() (voir POST /agent/actions/{id}/valider
    dans app/api/v1/endpoints/agent.py) — la réponse HTTP de validation
    ne doit jamais attendre l'appel réseau à l'API Meta.
  - Un brouillon ne peut être généré que pour un feedback qui a déjà une
    AnalyseIA persistée, sinon FeedbackNonAnalyseError est levée.
  - Le prompt envoyé au LLM ne contient que les données réellement
    récupérées (feedback + analyse), jamais une supposition.

Distinct de app/services/ai/recommandations.py (BF-17, templates statiques
internes à l'Agency Manager, inchangé) : ActionAgent porte un brouillon
généré par Mistral, potentiellement destiné AU CLIENT (WhatsApp) après
validation humaine.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.action_agent import ActionAgent
from app.models.analyse_ia import AnalyseIA
from app.models.enums import CriticiteType, StatutActionAgent, TypeActionAgent
from app.models.feedback import Feedback
from app.services.ai.agent import llm_provider, queries, whatsapp_provider

logger = logging.getLogger(__name__)


class FeedbackNonAnalyseError(RuntimeError):
    """Levée quand on tente de générer un brouillon pour un feedback sans AnalyseIA."""


class ActionInconnueError(RuntimeError):
    """Levée quand on référence un action_id qui n'existe pas."""


_SYSTEM_PROMPT_REPONSE_CLIENT = (
    "Tu rédiges un brouillon de réponse à un client d'un opérateur "
    "télécom, à partir de son feedback et de son analyse IA (sentiment, "
    "thème, criticité) fournis en JSON. Ton ton est empathique et "
    "professionnel. Tu ne fais JAMAIS de promesse chiffrée (pas de date "
    "précise de résolution, pas de montant de remboursement, pas de délai "
    "garanti). Termine toujours en rappelant que ce texte est un "
    "brouillon à relire et valider par un agent avant tout envoi."
)

_SYSTEM_PROMPT_TICKET_INTERNE = (
    "Tu rédiges un ticket interne à destination d'une équipe technique ou "
    "support d'un opérateur télécom, à partir d'un feedback client et de "
    "son analyse IA (sentiment, thème, criticité) fournis en JSON. "
    "Structure STRICTEMENT ta réponse avec ces sections : "
    "Contexte / Problème / Urgence / Action recommandée."
)


def _get_feedback_et_analyse(db: Session, feedback_id: uuid.UUID) -> tuple[Feedback | None, AnalyseIA | None]:
    feedback = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if feedback is None:
        return None, None
    analyse = db.query(AnalyseIA).filter(AnalyseIA.feedback_id == feedback_id).first()
    return feedback, analyse


def _build_user_prompt(feedback: Feedback, analyse: AnalyseIA) -> str:
    donnees = queries._serialize(feedback, analyse)  # noqa: SLF001 — même module logique, réutilise la sérialisation JSON-safe
    return (
        "Voici le feedback et son analyse IA, au format JSON :\n"
        f"{json.dumps(donnees, ensure_ascii=False)}"
    )


def generer_brouillon(db: Session, feedback_id: uuid.UUID, type_action: TypeActionAgent) -> ActionAgent:
    """
    Génère un brouillon d'action (réponse client ou ticket interne) pour un
    feedback déjà analysé.

    Lève FeedbackNonAnalyseError si aucune AnalyseIA n'existe pour ce feedback_id.
    """
    feedback, analyse = _get_feedback_et_analyse(db, feedback_id)
    if feedback is None or analyse is None:
        raise FeedbackNonAnalyseError(
            f"Aucune analyse IA existante pour le feedback '{feedback_id}'. "
            "Impossible de générer un brouillon sans contexte."
        )

    type_action = TypeActionAgent(type_action)
    system_prompt = (
        _SYSTEM_PROMPT_REPONSE_CLIENT
        if type_action == TypeActionAgent.REPONSE_CLIENT
        else _SYSTEM_PROMPT_TICKET_INTERNE
    )

    user_prompt = _build_user_prompt(feedback, analyse)
    contenu_genere = llm_provider.generate_text(system_prompt, user_prompt)

    action = ActionAgent(
        feedback_id=feedback_id,
        type_action=type_action,
        contenu_genere=contenu_genere,
        statut=StatutActionAgent.EN_ATTENTE,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def _get_action_or_raise(db: Session, action_id: uuid.UUID) -> ActionAgent:
    action = db.query(ActionAgent).filter(ActionAgent.id == action_id).first()
    if action is None:
        raise ActionInconnueError(f"Action '{action_id}' introuvable.")
    return action


def valider_action(db: Session, action_id: uuid.UUID, contenu_final: Optional[str] = None) -> ActionAgent:
    """
    Valide un brouillon d'action : passe son statut à VALIDEE.

    Ne déclenche PAS l'envoi WhatsApp ici — c'est la responsabilité de
    l'appelant (endpoint) de programmer tenter_envoi_whatsapp_action() en
    BackgroundTasks juste après avoir appelé cette fonction, pour que la
    réponse HTTP ne soit jamais bloquée par l'appel réseau à l'API Meta.
    """
    action = _get_action_or_raise(db, action_id)
    action.statut = StatutActionAgent.VALIDEE
    if contenu_final is not None:
        action.contenu_final = contenu_final
    db.commit()
    db.refresh(action)
    return action


def rejeter_action(db: Session, action_id: uuid.UUID) -> ActionAgent:
    """Rejette un brouillon d'action : passe son statut à REJETEE."""
    action = _get_action_or_raise(db, action_id)
    action.statut = StatutActionAgent.REJETEE
    db.commit()
    db.refresh(action)
    return action


def tenter_envoi_whatsapp_action(action_id: uuid.UUID) -> None:
    """
    Tente l'envoi WhatsApp pour une action déjà validée, et persiste le
    résultat dans les 3 colonnes dédiées (statut_envoi_whatsapp,
    whatsapp_message_id, whatsapp_erreur).

    Conçue pour être appelée via FastAPI BackgroundTasks : ouvre sa PROPRE
    session DB (la session de la requête d'origine est fermée dès que la
    réponse HTTP est envoyée). Ne lève jamais d'exception vers l'appelant.
    """
    db = SessionLocal()
    try:
        action = db.query(ActionAgent).filter(ActionAgent.id == action_id).first()
        if action is None:
            logger.warning(f"ActionAgent {action_id} introuvable pour l'envoi WhatsApp")
            return

        if action.type_action != TypeActionAgent.REPONSE_CLIENT:
            action.statut_envoi_whatsapp = "non_applicable"
            db.commit()
            return

        feedback = db.query(Feedback).filter(Feedback.id == action.feedback_id).first()
        numero = feedback.demande_contact.telephone if feedback and feedback.demande_contact else None
        if not numero:
            action.statut_envoi_whatsapp = "ignore"
            db.commit()
            return

        contenu = action.contenu_final or action.contenu_genere
        try:
            resultat = whatsapp_provider.envoyer_message_template(
                numero_destinataire=numero,
                nom_template=settings.WHATSAPP_TEMPLATE_NAME,
                code_langue=settings.WHATSAPP_TEMPLATE_LANG,
                parametres_corps=[contenu],
            )
            action.statut_envoi_whatsapp = "envoye"
            messages = resultat.get("messages") or []
            action.whatsapp_message_id = messages[0].get("id") if messages else None
            action.whatsapp_erreur = None
        except whatsapp_provider.WhatsAppProviderError as e:
            action.statut_envoi_whatsapp = "echec"
            action.whatsapp_erreur = str(e)

        db.commit()
    except Exception as e:
        logger.error(f"Erreur inattendue lors de l'envoi WhatsApp pour l'action {action_id}: {e}")
        db.rollback()
    finally:
        db.close()


_CRITICITES_DECLENCHANT_ALERTE = {CriticiteType.ELEVEE, CriticiteType.CRITIQUE}


def declencher_alerte_si_critique(feedback_id: uuid.UUID, db: Session) -> Optional[ActionAgent]:
    """
    Point d'entrée appelé juste après la persistance d'une AnalyseIA (voir
    analyser_feedback() dans app/services/ai/analyse_service.py, même bloc
    try que la génération des Recommandation BF-17 — les deux mécanismes
    sont indépendants et coexistent).

    Si la criticité est Élevée ou Critique, génère automatiquement un
    brouillon de réponse client (ActionAgent, statut EN_ATTENTE) — qui
    apparaît dans la liste des actions en attente du dashboard. Le manager
    valide ou modifie ; l'envoi WhatsApp ne se déclenche QUE s'il valide
    ET que le client a laissé un numéro de contact (voir
    tenter_envoi_whatsapp_action).

    Retourne None si la criticité ne déclenche pas d'alerte (comportement
    normal pour la majorité des feedbacks) ou si l'appel LLM échoue — une
    panne de génération de brouillon ne doit jamais faire échouer
    l'analyse du feedback elle-même.
    """
    analyse = db.query(AnalyseIA).filter(AnalyseIA.feedback_id == feedback_id).first()
    if analyse is None or analyse.criticite not in _CRITICITES_DECLENCHANT_ALERTE:
        return None

    try:
        return generer_brouillon(db, feedback_id, TypeActionAgent.REPONSE_CLIENT)
    except llm_provider.LLMProviderError as e:
        logger.error(f"Échec de génération du brouillon d'alerte pour le feedback {feedback_id}: {e}")
        return None
