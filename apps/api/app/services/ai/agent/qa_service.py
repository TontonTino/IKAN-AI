"""
Service de Question/Réponse pour les managers.

Porté depuis le prototype (Agent IA/app/agent/qa_service.py) vers
SQLAlchemy : mock_store.get_feedbacks est remplacé par
queries._get_feedbacks (même helper que celui utilisé par les fonctions de
requête, voir NOTE DE PORTAGE dans queries.py), le reste de la logique est
inchangé.

Flux strict (règle architecturale n°1) :
  1. classifier_intention() détermine l'intention SANS jamais passer par
     le LLM.
  2. La fonction de requête correspondante va chercher les données dans
     la base réelle (Feedback + AnalyseIA, via SQLAlchemy).
  3. Un prompt Mistral est construit avec UNIQUEMENT ces données réelles
     (règle n°5 : jamais de supposition envoyée au LLM).
  4. Si l'intention est "autre", on répond avec un message fixe SANS
     appeler le LLM du tout.

Étendu par rapport au prototype (intentions.yaml n'avait que 4 intentions
réelles) : problemes_recurrents, tendances_anomalies et
evolution_satisfaction s'appuient sur les fonctions déjà présentes dans
queries.py (query_problemes_recurrents, comparer_periodes,
query_evolution_satisfaction).
"""

from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.ai.agent import llm_provider, queries
from app.services.ai.agent.intent_classifier import classifier_intention

MESSAGE_HORS_PERIMETRE = "je ne sais pas répondre à ça dans ce cadre"

_SYSTEM_PROMPT_BASE = (
    "Tu es l'assistant d'analyse de feedbacks clients d'IKANAI, pour un "
    "opérateur télécom. Tu réponds UNIQUEMENT à partir des données JSON "
    "fournies dans le message utilisateur. Tu n'inventes jamais de chiffre "
    "ou de feedback qui n'est pas dans ces données. Réponds en français, "
    "de façon concise et utile pour un manager d'agence."
)


def _resume_agregats(feedbacks: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(feedbacks)
    critiques = sum(1 for f in feedbacks if f["criticite"] == "critique")
    elevees = sum(1 for f in feedbacks if f["criticite"] == "elevee")

    par_theme: dict[str, int] = {}
    for f in feedbacks:
        theme = f["theme_principal"]
        par_theme[theme] = par_theme.get(theme, 0) + 1
    top_themes = sorted(par_theme.items(), key=lambda item: item[1], reverse=True)[:3]

    return {
        "total": total,
        "critiques": critiques,
        "elevees": elevees,
        "top_themes": [{"theme": theme, "count": count} for theme, count in top_themes],
    }


def repondre_question(
    db: Session, question: str, agence_id: Optional[UUID] = None, jours: int = 7
) -> dict[str, Any]:
    """
    Répond à une question en langage naturel d'un manager.

    Retourne {'intention': str, 'reponse': str, 'donnees': Any}.
    """
    intention = classifier_intention(question)

    if intention == "autre":
        return {"intention": "autre", "reponse": MESSAGE_HORS_PERIMETRE, "donnees": None}

    if intention == "alertes_critiques":
        donnees = queries.query_alertes_critiques(db, agence_id=agence_id, jours=jours)
        user_prompt = (
            "Voici la liste des feedbacks d'alerte critique (criticité "
            "élevée ou critique) des derniers jours, au format JSON :\n"
            f"{json.dumps(donnees, ensure_ascii=False)}\n\n"
            "Résume ces alertes pour un manager d'agence : combien il y en "
            "a, quels thèmes reviennent, et ce qui mérite une action "
            "rapide."
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
        feedbacks = queries._get_feedbacks(db, agence_id, jours)  # noqa: SLF001 — même module logique, réutilise la sérialisation JSON-safe
        donnees = _resume_agregats(feedbacks)
        user_prompt = (
            "Voici les agrégats de l'activité feedbacks sur la période, au "
            f"format JSON :\n{json.dumps(donnees, ensure_ascii=False)}\n\n"
            "Rédige un résumé en langage naturel de l'activité récente pour "
            "un manager d'agence, en mettant en avant les points "
            "d'attention."
        )

    elif intention == "problemes_recurrents":
        donnees = queries.query_problemes_recurrents(db, agence_id=agence_id, jours=jours)
        user_prompt = (
            "Voici les problèmes récurrents (même agence + même thème "
            f"signalés plusieurs fois), au format JSON :\n"
            f"{json.dumps(donnees, ensure_ascii=False)}\n\n"
            "Présente-les pour un manager d'agence, en mettant en avant "
            "ceux avec la criticité la plus élevée et les plus fréquents."
        )

    elif intention == "tendances_anomalies":
        donnees = queries.comparer_periodes(db, agence_id=agence_id, jours_periode=jours)
        user_prompt = (
            "Voici la comparaison entre la période actuelle et la période "
            f"précédente, au format JSON :\n{json.dumps(donnees, ensure_ascii=False)}\n\n"
            "Explique pour un manager d'agence ce qui a changé et signale "
            "clairement les anomalies détectées, s'il y en a."
        )

    elif intention == "evolution_satisfaction":
        donnees = queries.query_evolution_satisfaction(db, agence_id=agence_id, jours_periode=jours)
        user_prompt = (
            "Voici l'évolution du sentiment moyen sur plusieurs périodes "
            f"consécutives, au format JSON :\n{json.dumps(donnees, ensure_ascii=False)}\n\n"
            "Décris pour un manager d'agence la tendance de satisfaction "
            "client (amélioration, dégradation, stabilité)."
        )

    else:
        # Filet de sécurité si intentions.yaml évolue sans que ce service
        # ne soit mis à jour en conséquence.
        return {"intention": "autre", "reponse": MESSAGE_HORS_PERIMETRE, "donnees": None}

    reponse = llm_provider.generate_text(_SYSTEM_PROMPT_BASE, user_prompt)

    return {"intention": intention, "reponse": reponse, "donnees": donnees}
