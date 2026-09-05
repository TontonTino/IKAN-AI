"""
Gestion de la mémoire conversationnelle — persiste et recharge le contexte
actif et l'historique des tours (voir app/models/conversation.py pour le
détail des deux tables `conversations` / `conversation_turns`).

RÈGLE DE ROBUSTESSE : ce module ne doit JAMAIS être la cause d'un échec de
Q&A. Il ne s'auto-protège pas lui-même (pas de try/except interne) — c'est
la responsabilité de l'appelant (app.agent.qa_service.repondre_question) de
l'encapsuler et de retomber en mode dégradé (stateless) si une opération
échoue. Voir la docstring de repondre_question().
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.conversation import Conversation, ConversationTurn

logger = logging.getLogger(__name__)

# Nombre max de tours passés inclus dans l'historique envoyé au LLM — la
# fenêtre de contexte de Groq compound-mini est limitée, et un historique
# non borné finirait par la dépasser silencieusement.
_MAX_TOURS_HISTORIQUE = 5

# Nombre max d'éléments gardés dans un aperçu de données condensées.
_MAX_ELEMENTS_APERCU = 3


def get_or_create_conversation(
    db: Session,
    conversation_id: Optional[uuid.UUID],
    utilisateur_id: Optional[uuid.UUID],
    agence_id: Optional[uuid.UUID],
) -> Conversation:
    """
    Charge la conversation existante ou en crée une nouvelle.

    Si `conversation_id` est fourni mais ne correspond à aucune conversation
    existante (id invalide, expirée côté client...), une NOUVELLE conversation
    est créée plutôt que de lever une erreur — un identifiant de conversation
    inconnu ne doit jamais bloquer une question.
    """
    if conversation_id is not None:
        conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conversation is not None:
            logger.info(f"Conversation {conversation.id} reprise (existante, pas recréée)")
            return conversation

    conversation = Conversation(
        id=uuid.uuid4(),
        agence_id=agence_id,
        utilisateur_id=utilisateur_id,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    logger.info(f"Conversation {conversation.id} créée")
    return conversation


def get_recent_turns(
    db: Session,
    conversation_id: uuid.UUID,
    limit: int = 5,
) -> list[ConversationTurn]:
    """Retourne les N derniers tours, ordonnés du plus ancien au plus récent."""
    tours_bruts = (
        db.query(ConversationTurn)
        .filter(ConversationTurn.conversation_id == conversation_id)
        .order_by(ConversationTurn.tour_numero.desc())
        .limit(limit)
        .all()
    )
    tours = list(reversed(tours_bruts))
    logger.info(f"{len(tours)} tour(s) précédent(s) chargé(s) pour la conversation {conversation_id}")
    return tours


def _resumer_donnees(donnees: Any) -> Any:
    """
    Condense `donnees` pour stockage dans ConversationTurn.donnees_resumees :
    ne garde jamais la totalité (une liste de dizaines de feedbacks
    gonflerait l'historique conversationnel pour rien), seulement un aperçu
    exploitable + le compte total.
    """
    if isinstance(donnees, list):
        return {
            "nombre_total": len(donnees),
            "apercu": donnees[:_MAX_ELEMENTS_APERCU],
        }
    if isinstance(donnees, dict):
        resume: dict[str, Any] = {}
        for cle, valeur in donnees.items():
            if isinstance(valeur, list) and len(valeur) > _MAX_ELEMENTS_APERCU:
                resume[cle] = {
                    "nombre_total": len(valeur),
                    "apercu": valeur[:_MAX_ELEMENTS_APERCU],
                }
            else:
                resume[cle] = valeur
        return resume
    return donnees


def save_turn(
    db: Session,
    conversation_id: uuid.UUID,
    question: str,
    intention: str,
    reponse: str,
    donnees: Any,
) -> ConversationTurn:
    """
    Enregistre un nouveau tour (numéroté séquentiellement dans la
    conversation) avec une version condensée des données.

    NE met PAS à jour `contexte_actif` (qui a besoin de `agence_id`/`jours`,
    non disponibles ici) — c'est le rôle de update_contexte_actif(),
    appelée séparément par l'appelant juste après.
    """
    dernier = (
        db.query(ConversationTurn.tour_numero)
        .filter(ConversationTurn.conversation_id == conversation_id)
        .order_by(ConversationTurn.tour_numero.desc())
        .first()
    )
    tour_numero = (dernier[0] + 1) if dernier is not None else 1

    tour = ConversationTurn(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        tour_numero=tour_numero,
        question=question,
        intention=intention,
        reponse=reponse,
        donnees_resumees=_resumer_donnees(donnees),
    )
    db.add(tour)
    db.commit()
    db.refresh(tour)
    return tour


def _extraire_agence_nom(donnees: Any) -> Optional[str]:
    """
    Best-effort : cherche un 'agence_nom' dans les données du tour (présent
    sur la plupart des structures retournées par app.agent.queries — voir
    _ligne_vers_dict()). Purement indicatif, pas une garantie — retourne
    None si la forme des données ne s'y prête pas.
    """
    items: list[Any]
    if isinstance(donnees, list):
        items = donnees
    elif isinstance(donnees, dict):
        items = [donnees]
    else:
        items = []

    for item in items:
        if isinstance(item, dict) and item.get("agence_nom"):
            return item["agence_nom"]
    return None


def _extraire_sujet_actif(donnees: Any) -> Optional[str]:
    """
    Best-effort : dérive un 'sujet actif' à partir du thème principal le
    plus fréquent dans les données du tour, quand disponible. Purement
    indicatif — ce n'est pas une extraction sémantique fiable, seulement un
    signal utile pour une future résolution de référence ("ce problème").
    """
    if not isinstance(donnees, list):
        return None
    themes = [
        item.get("theme_principal")
        for item in donnees
        if isinstance(item, dict) and item.get("theme_principal")
    ]
    if not themes:
        return None
    return max(set(themes), key=themes.count)


def update_contexte_actif(
    db: Session,
    conversation: Conversation,
    intention: str,
    donnees: Any,
    agence_id: Optional[uuid.UUID],
    jours: int,
) -> None:
    """
    Met à jour le JSON contexte_actif avec les informations du tour courant
    (fusion avec le contexte existant, jamais un remplacement complet — un
    champ non renseigné ce tour-ci garde sa dernière valeur connue).
    """
    contexte: dict[str, Any] = dict(conversation.contexte_actif or {})

    if agence_id is not None:
        contexte["agence_id"] = str(agence_id)
    agence_nom = _extraire_agence_nom(donnees)
    if agence_nom is not None:
        contexte["agence_nom"] = agence_nom

    contexte["periode_jours"] = jours
    contexte["intention_precedente"] = intention

    sujet_actif = _extraire_sujet_actif(donnees)
    if sujet_actif is not None:
        contexte["sujet_actif"] = sujet_actif

    contexte["derniere_donnee_cle"] = _resumer_donnees(donnees)

    conversation.contexte_actif = contexte
    db.add(conversation)
    db.commit()


def build_messages_history(
    turns: list[ConversationTurn],
    system_prompt: str,
    current_user_prompt: str,
) -> list[dict]:
    """
    Construit la liste de messages OpenAI-compatible pour le LLM :
    [
      {"role": "system", "content": system_prompt},
      {"role": "user", "content": turns[0].question},
      {"role": "assistant", "content": turns[0].reponse},
      ...
      {"role": "user", "content": current_user_prompt},
    ]

    Limite à _MAX_TOURS_HISTORIQUE tours (les plus récents) même si `turns`
    en contient davantage — défense en profondeur, get_recent_turns() borne
    déjà la requête DB, mais cette fonction ne doit jamais dépendre de la
    discipline de son appelant pour rester dans une fenêtre de contexte
    raisonnable.
    """
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    for tour in turns[-_MAX_TOURS_HISTORIQUE:]:
        messages.append({"role": "user", "content": tour.question})
        messages.append({"role": "assistant", "content": tour.reponse})

    messages.append({"role": "user", "content": current_user_prompt})
    return messages
