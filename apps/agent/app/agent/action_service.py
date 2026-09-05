"""
Service de génération et de gestion des brouillons d'action. CONVERTI depuis
le prototype : mock_store remplacé par de vraies requêtes SQLAlchemy sur la
table actions_agent (propriété de ce service).

Règles conservées du prototype :
  - Tout brouillon créé a le statut EN_ATTENTE.
  - Un brouillon ne peut être généré que pour un feedback qui a déjà une
    analyse IA existante, sinon FeedbackNonAnalyseError est levée.
  - Le prompt envoyé au LLM ne contient que les données réellement
    récupérées (feedback + analyse), jamais une supposition.

CHANGEMENT par rapport au prototype (imposé par l'intégration réelle) :
  - `valider_action()` ne fait plus QUE changer le statut de façon
    synchrone (aucun appel réseau). L'envoi WhatsApp est désormais une
    fonction séparée, `envoyer_whatsapp_si_applicable()`, destinée à être
    planifiée en FastAPI BackgroundTasks depuis l'endpoint — elle ouvre sa
    PROPRE session DB (la session de la requête HTTP est fermée avant que
    la tâche de fond ne s'exécute). Les 3 colonnes WhatsApp
    (statut_envoi_whatsapp, whatsapp_message_id, whatsapp_erreur) sont
    mises à jour par cette tâche une fois terminée.
  - Le numéro de contact vient de `feedback.demande_contact.telephone`
    (relation réelle), et non plus de `feedback["contact_telephone"]`
    (champ à plat du mock).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.agent import queries
from app.db.session import SessionLocal
from app.models.action_agent import ActionAgent
from app.models.enums import StatutActionAgent, TypeActionAgent, CriticiteType
from app.models.readonly import AnalyseIA
from app.config.settings import settings
from app.providers import llm_provider, whatsapp_provider


class FeedbackNonAnalyseError(RuntimeError):
    """Levée quand on tente de générer un brouillon pour un feedback sans analyse IA."""


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


def _build_user_prompt(analyse: dict) -> str:
    import json

    return (
        "Voici le feedback et son analyse IA, au format JSON :\n"
        f"{json.dumps(analyse, ensure_ascii=False)}"
    )


def generer_brouillon(
    db: Session, feedback_id: uuid.UUID, type_action: TypeActionAgent
) -> ActionAgent:
    """
    Génère un brouillon d'action (réponse client ou ticket interne) pour un
    feedback déjà analysé.

    Lève FeedbackNonAnalyseError si aucune analyse IA n'existe pour ce
    feedback_id.
    """
    analyse_dict = queries.get_feedback_with_analyse(db, feedback_id)
    if analyse_dict is None:
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

    user_prompt = _build_user_prompt(analyse_dict)
    contenu_genere = llm_provider.generate_text(system_prompt, user_prompt)

    action = ActionAgent(
        id=uuid.uuid4(),
        feedback_id=feedback_id,
        type_action=type_action,
        contenu_genere=contenu_genere,
        contenu_final=None,
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


def valider_action(
    db: Session,
    action_id: uuid.UUID,
    valide_par_id: uuid.UUID,
    contenu_final: Optional[str] = None,
) -> ActionAgent:
    """
    Valide un brouillon d'action : passe son statut à VALIDEE (opération
    synchrone, aucun appel réseau). L'envoi WhatsApp éventuel est déclenché
    séparément par l'appelant via BackgroundTasks — voir
    envoyer_whatsapp_si_applicable().
    """
    action = _get_action_or_raise(db, action_id)
    action.statut = StatutActionAgent.VALIDEE
    action.valide_par_id = valide_par_id
    action.valide_le = datetime.now(timezone.utc)
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


def envoyer_whatsapp_si_applicable(action_id: uuid.UUID) -> None:
    """
    Tâche de fond : tente l'envoi WhatsApp pour une action tout juste
    validée, et persiste le résultat. Ouvre sa PROPRE session DB — ne
    jamais lui passer la session de la requête HTTP d'origine, elle est
    fermée au moment où cette fonction s'exécute (BackgroundTasks tourne
    après l'envoi de la réponse HTTP).

    Ne lève jamais d'exception : toute erreur est capturée et écrite dans
    whatsapp_erreur pour que le manager puisse la consulter.
    """
    db = SessionLocal()
    try:
        action = db.query(ActionAgent).filter(ActionAgent.id == action_id).first()
        if action is None:
            return

        if action.type_action != TypeActionAgent.REPONSE_CLIENT:
            action.statut_envoi_whatsapp = "non_applicable"
            db.commit()
            return

        feedback_dict = queries.get_feedback_with_analyse(db, action.feedback_id)
        numero = feedback_dict.get("contact_telephone") if feedback_dict else None
        if not numero:
            action.statut_envoi_whatsapp = "ignore"
            action.whatsapp_erreur = "Aucun numéro de contact laissé par le client."
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
            action.whatsapp_message_id = (
                resultat.get("messages", [{}])[0].get("id") if isinstance(resultat, dict) else None
            )
            action.whatsapp_erreur = None
        except whatsapp_provider.WhatsAppProviderError as e:
            action.statut_envoi_whatsapp = "echec"
            action.whatsapp_erreur = str(e)

        db.commit()
    finally:
        db.close()


_CRITICITES_DECLENCHANT_ALERTE = {CriticiteType.ELEVEE, CriticiteType.CRITIQUE}


def declencher_alerte_si_critique(db: Session, feedback_id: uuid.UUID) -> Optional[ActionAgent]:
    """
    Point d'entrée appelé par le webhook /webhook/analyse-complete, juste
    après la création d'une AnalyseIA côté backend principal.

    Si la criticité est Élevée ou Critique, génère automatiquement un
    brouillon de réponse client. Idempotent : si un brouillon
    REPONSE_CLIENT existe déjà pour ce feedback (ex. appel webhook
    dupliqué/retry), le retourne tel quel plutôt que d'en créer un second.

    Retourne None si la criticité ne déclenche pas d'alerte — comportement
    attendu pour la majorité des feedbacks, pas une erreur.
    """
    analyse = db.query(AnalyseIA).filter(AnalyseIA.feedback_id == feedback_id).first()
    if analyse is None or analyse.criticite not in _CRITICITES_DECLENCHANT_ALERTE:
        return None

    existante = (
        db.query(ActionAgent)
        .filter(
            ActionAgent.feedback_id == feedback_id,
            ActionAgent.type_action == TypeActionAgent.REPONSE_CLIENT,
        )
        .first()
    )
    if existante is not None:
        return existante

    return generer_brouillon(db, feedback_id, TypeActionAgent.REPONSE_CLIENT)
