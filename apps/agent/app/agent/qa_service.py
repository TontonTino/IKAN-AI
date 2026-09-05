"""
Service de Question/Réponse pour les managers. CONVERTI depuis le prototype :
mock_store remplacé par de vraies requêtes SQLAlchemy (app.agent.queries),
chaque fonction reçoit désormais une session `db` explicite.

Flux strict (conservé du prototype) :
  1. classifier_intention() détermine l'intention SANS jamais passer par le LLM.
  2. La fonction de requête correspondante va chercher les données en base.
  3. Un prompt Mistral/Groq est construit avec UNIQUEMENT ces données réelles.
  4. Si l'intention est "autre", on répond avec un message fixe SANS
     appeler le LLM du tout.

MÉMOIRE CONVERSATIONNELLE (voir app.agent.conversation_manager) :
  - Chaque appel charge/crée une Conversation et ses derniers tours, puis
    construit l'historique de messages envoyé au LLM.
  - Chaque appel persiste le tour courant et met à jour le contexte actif
    de la conversation.
  - RÈGLE : la mémoire est TOUJOURS best-effort. Toute panne côté
    ConversationManager (DB indisponible, etc.) est capturée, journalisée
    en WARNING, et le Q&A continue en mode dégradé (stateless) — jamais
    d'échec de la question à cause de la mémoire.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.agent import conversation_manager, queries
from app.agent.intent_classifier import classifier_intention
from app.models.conversation import Conversation, ConversationTurn
from app.providers import llm_provider

logger = logging.getLogger(__name__)

MESSAGE_HORS_PERIMETRE = "je ne sais pas répondre à ça dans ce cadre"

_SYSTEM_PROMPT_BASE = (
    "Tu es l'assistant d'analyse de feedbacks clients d'IKANAI, pour un "
    "opérateur télécom. Tu réponds UNIQUEMENT à partir des données JSON "
    "fournies dans le message utilisateur. Tu n'inventes jamais de chiffre "
    "ou de feedback qui n'est pas dans ces données. "
    "IMPORTANT : le champ 'agence_nom' est le SEUL identifiant officiel de "
    "lieu à utiliser dans ta réponse. Le champ 'commentaire' est le texte "
    "libre écrit par le client — il peut mentionner un quartier, un point "
    "de repère, ou un autre nom de lieu qui NE correspond PAS forcément à "
    "l'agence administrative à laquelle le feedback est rattaché. Ne "
    "présente jamais un lieu mentionné uniquement dans 'commentaire' comme "
    "s'il s'agissait du nom officiel d'une agence — cite-le au maximum "
    "comme précision du client entre guillemets, jamais comme identifiant "
    "de lieu à traiter. Réponds en français, de façon concise et utile "
    "pour un manager d'agence."
)


def _resume_agregats(feedbacks: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(feedbacks)
    critiques = sum(1 for f in feedbacks if f["criticite"] == "critique")
    elevees = sum(1 for f in feedbacks if f["criticite"] == "elevee")

    par_theme: dict[str, int] = {}
    sentiment_par_theme: dict[str, list[float]] = {}
    for f in feedbacks:
        theme = f["theme_principal"]
        par_theme[theme] = par_theme.get(theme, 0) + 1
        sentiment_par_theme.setdefault(theme, []).append(f["sentiment_score"])
    top_themes = sorted(par_theme.items(), key=lambda item: item[1], reverse=True)[:3]

    moyennes_theme = {
        theme: sum(scores) / len(scores) for theme, scores in sentiment_par_theme.items()
    }
    theme_plus_negatif = min(moyennes_theme.items(), key=lambda x: x[1]) if moyennes_theme else None

    return {
        "total": total,
        "critiques": critiques,
        "elevees": elevees,
        "top_themes": [{"theme": theme, "count": count} for theme, count in top_themes],
        "theme_sentiment_le_plus_negatif": (
            {"theme": theme_plus_negatif[0], "sentiment_moyen": round(theme_plus_negatif[1], 3)}
            if theme_plus_negatif else None
        ),
    }


def _charger_memoire(
    db: Session,
    conversation_id: Optional[uuid.UUID],
    utilisateur_id: Optional[uuid.UUID],
    agence_id: Optional[uuid.UUID],
) -> tuple[Optional[Conversation], list[ConversationTurn]]:
    """
    Charge (ou crée) la conversation et ses derniers tours — best-effort :
    toute exception est capturée ici, journalisée en WARNING, et le Q&A
    continue en mode dégradé (conversation=None, aucun historique).
    """
    try:
        conversation = conversation_manager.get_or_create_conversation(
            db, conversation_id, utilisateur_id, agence_id
        )
        turns = conversation_manager.get_recent_turns(db, conversation.id)
        return conversation, turns
    except Exception:
        logger.warning(
            "ConversationManager indisponible (chargement) — Q&A en mode "
            "dégradé, sans mémoire conversationnelle.",
            exc_info=True,
        )
        try:
            db.rollback()
        except Exception:
            pass
        return None, []


def _finaliser_tour(
    db: Session,
    conversation: Optional[Conversation],
    conversation_id_effectif: uuid.UUID,
    question: str,
    intention: str,
    reponse: str,
    donnees: Any,
    agence_id: Optional[uuid.UUID],
    jours: int,
) -> dict[str, Any]:
    """
    Persiste le tour courant (best-effort — voir _charger_memoire) et
    construit le résultat final avec conversation_id.
    """
    if conversation is not None:
        try:
            conversation_manager.save_turn(db, conversation.id, question, intention, reponse, donnees)
            conversation_manager.update_contexte_actif(db, conversation, intention, donnees, agence_id, jours)
        except Exception:
            logger.warning(
                "ConversationManager indisponible (sauvegarde) — ce tour "
                "n'a pas été mémorisé.",
                exc_info=True,
            )
            try:
                db.rollback()
            except Exception:
                pass

    return {
        "intention": intention,
        "reponse": reponse,
        "donnees": donnees,
        "conversation_id": conversation_id_effectif,
    }


def repondre_question(
    db: Session,
    question: str,
    agence_id: Optional[uuid.UUID] = None,
    jours: int = 7,
    conversation_id: Optional[uuid.UUID] = None,
    utilisateur_id: Optional[uuid.UUID] = None,
) -> dict[str, Any]:
    """
    Répond à une question en langage naturel d'un manager.

    Retourne {'intention': str, 'reponse': str, 'donnees': Any,
    'conversation_id': UUID}. `conversation_id` est toujours renvoyé (même
    en mode dégradé, où il est généré localement sans être persisté) — le
    client le renvoie au tour suivant pour poursuivre la conversation.
    """
    conversation, turns_precedents = _charger_memoire(db, conversation_id, utilisateur_id, agence_id)
    conversation_id_effectif = conversation.id if conversation is not None else (conversation_id or uuid.uuid4())

    intention = classifier_intention(question)

    if intention == "autre":
        return _finaliser_tour(
            db, conversation, conversation_id_effectif, question, "autre",
            MESSAGE_HORS_PERIMETRE, None, agence_id, jours,
        )

    if intention == "alertes_critiques":
        donnees = queries.query_alertes_critiques(db, agence_id=agence_id, jours=jours)
        user_prompt = (
            "Voici la liste des feedbacks d'alerte critique (criticité "
            "élevée ou critique) des derniers jours, DÉJÀ TRIÉE par ordre "
            "de priorité décroissant (champ 'score_priorite', qui combine "
            "criticité, fraîcheur et fréquence du thème), au format JSON :\n"
            f"{json.dumps(donnees, ensure_ascii=False)}\n\n"
            "Présente ces alertes pour un manager d'agence DANS L'ORDRE DE "
            "PRIORITÉ fourni (ne les retrie pas toi-même) : lesquelles "
            "traiter en premier et pourquoi, quels thèmes reviennent."
        )

    elif intention == "statistiques_theme":
        donnees = queries.query_statistiques_theme(db, agence_id=agence_id, jours=jours)
        user_prompt = (
            "Voici la répartition des feedbacks par thème sur la période, "
            f"au format JSON :\n{json.dumps(donnees, ensure_ascii=False)}\n\n"
            "Présente cette répartition de façon claire pour un manager "
            "d'agence."
        )

    elif intention == "a_verifier":
        donnees = queries.query_a_verifier(db, agence_id=agence_id, jours=jours)
        user_prompt = (
            "Voici les feedbacks signalés comme nécessitant une "
            f"vérification manuelle, au format JSON :\n"
            f"{json.dumps(donnees, ensure_ascii=False)}\n\n"
            "Liste-les pour un manager d'agence en indiquant pourquoi "
            "chacun mérite d'être vérifié (utilise les infos disponibles : "
            "note, commentaire, criticité)."
        )

    elif intention == "resume_periode":
        feedbacks = queries.get_feedbacks(db, agence_id=agence_id, jours=jours)
        donnees = _resume_agregats(feedbacks)
        user_prompt = (
            "Voici les agrégats de l'activité feedbacks sur la période, au "
            f"format JSON :\n{json.dumps(donnees, ensure_ascii=False)}\n\n"
            "Rédige un résumé en langage naturel de l'activité récente pour "
            "un manager d'agence. Utilise le champ "
            "'theme_sentiment_le_plus_negatif' pour EXPLIQUER quelle est la "
            "cause principale probable de l'insatisfaction sur cette "
            "période (pas seulement lister les chiffres — dis POURQUOI ce "
            "thème ressort), puis mets en avant les points d'attention."
        )

    elif intention == "problemes_recurrents":
        donnees = queries.query_problemes_recurrents(db, agence_id=agence_id, jours=max(jours, 30))
        user_prompt = (
            "Voici les problèmes récurrents détectés (même thème signalé "
            "plusieurs fois dans la même agence), au format JSON :\n"
            f"{json.dumps(donnees, ensure_ascii=False)}\n\n"
            "Explique à un manager d'agence quels problèmes reviennent "
            "le plus souvent, où, et depuis quand (utilise "
            "'derniere_occurrence'). Si la liste est vide, dis clairement "
            "qu'aucun problème récurrent n'a été détecté sur la période."
        )

    elif intention == "tendances_anomalies":
        donnees = queries.comparer_periodes(db, agence_id=agence_id, jours_periode=jours)
        user_prompt = (
            "Voici une comparaison entre la période actuelle et la période "
            "précédente de même durée, avec les anomalies déjà détectées "
            f"(champ 'anomalies'), au format JSON :\n"
            f"{json.dumps(donnees, ensure_ascii=False)}\n\n"
            "Explique à un manager d'agence ce qui a changé par rapport à "
            "la période précédente. Si 'anomalies' est vide, dis "
            "clairement qu'aucune variation significative n'a été détectée "
            "— n'invente pas une tendance qui n'est pas dans les données."
        )

    elif intention == "evolution_satisfaction":
        donnees = queries.query_evolution_satisfaction(db, agence_id=agence_id, jours_periode=min(jours, 7))
        user_prompt = (
            "Voici l'évolution du sentiment moyen sur plusieurs périodes "
            f"consécutives, de la plus ancienne à la plus récente, au format JSON :\n"
            f"{json.dumps(donnees, ensure_ascii=False)}\n\n"
            "Décris à un manager d'agence comment la satisfaction client a "
            "évolué dans le temps : amélioration, dégradation, ou stable. "
            "Base-toi uniquement sur les valeurs 'sentiment_moyen' fournies "
            "(null = pas assez de données sur cette période, dis-le si "
            "c'est le cas plutôt que de l'ignorer)."
        )

    elif intention == "predictions_risques":
        donnees = queries.query_predictions(db, agence_id=agence_id, jours_periode=jours)
        if donnees.get("donnees_insuffisantes"):
            return _finaliser_tour(
                db, conversation, conversation_id_effectif, question, intention,
                (
                    "Pas encore assez de données pour établir des prédictions "
                    "fiables. Continuez à collecter des feedbacks."
                ),
                donnees, agence_id, jours,
            )
        user_prompt = (
            "Voici les risques et opportunités détectés par comparaison entre "
            "la période actuelle et la période précédente, au format JSON :\n"
            f"{json.dumps(donnees, ensure_ascii=False)}\n\n"
            "Pour un manager d'agence, formule chaque risque et chaque "
            "opportunité en langage clair, sans jargon statistique. Pour "
            "CHAQUE risque, propose une recommandation d'action concrète et "
            "réalisable qui découle directement du signal fourni (jamais une "
            "généralité du type 'faites attention à ce thème'). Si "
            "'risques' et 'opportunites' sont tous les deux vides, dis "
            "clairement qu'aucun signal notable n'a été détecté sur la "
            "période — n'en invente pas."
        )

    else:
        # Filet de sécurité si intentions.yaml évolue sans que ce service
        # ne soit mis à jour en conséquence.
        return _finaliser_tour(
            db, conversation, conversation_id_effectif, question, "autre",
            MESSAGE_HORS_PERIMETRE, None, agence_id, jours,
        )

    messages = conversation_manager.build_messages_history(turns_precedents, _SYSTEM_PROMPT_BASE, user_prompt)
    logger.info(
        f"Appel LLM pour intention='{intention}' avec {len(turns_precedents)} "
        f"tour(s) d'historique ({len(messages)} message(s) au total transmis au LLM)"
    )
    reponse = llm_provider.generate_text(_SYSTEM_PROMPT_BASE, user_prompt, messages_history=messages)

    return _finaliser_tour(
        db, conversation, conversation_id_effectif, question, intention, reponse, donnees, agence_id, jours,
    )
