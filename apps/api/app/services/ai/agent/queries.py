"""
Fonctions de requête — une par intention Q&A du manager.

Portées depuis le prototype (Agent IA/app/agent/queries.py). Ces fonctions
interrogent UNIQUEMENT la base réelle (Feedback + AnalyseIA, via
SQLAlchemy) — mock_store.py du prototype n'existe plus ici. Elles ne font
jamais appel au LLM et ne renvoient jamais de données inventées : toute
détection de tendance/anomalie/priorité est un calcul statistique
déterministe, jamais une estimation du LLM.

NOTE DE PORTAGE — un champ du prototype n'a pas d'équivalent direct dans
le schéma réel ; un choix par défaut documentable a été fait (à réévaluer
si besoin) :
  - sentiment_score : AnalyseIA.score_sentiment est aujourd'hui toujours
    NULL (voir app/services/ai/analyse_service.py, "Géré en interne par
    la pipeline"). En son absence, on dérive un score signé -1/0/+1 depuis
    l'enum `sentiment` (POSITIF/NEUTRE/NEGATIF), pour ne jamais produire
    un résumé ou une évolution silencieusement vide.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.models.feedback import Feedback
from app.models.analyse_ia import AnalyseIA
from app.models.qr_code import QRCode
from app.models.enums import SentimentType

_CRITICITES_ALERTE = {"elevee", "critique"}

_POIDS_CRITICITE = {"faible": 0.1, "moyenne": 0.4, "elevee": 0.7, "critique": 1.0}
_SEUIL_RECURRENCE = 2  # nb minimum d'occurrences (même thème + même agence) pour être "récurrent"
_SEUIL_VARIATION_ANOMALIE = 0.3  # variation relative (30%) au-delà de laquelle on signale une anomalie

_SENTIMENT_SCORE_FALLBACK = {
    SentimentType.POSITIF: 1.0,
    SentimentType.NEUTRE: 0.0,
    SentimentType.NEGATIF: -1.0,
}


def _sentiment_score(analyse: AnalyseIA) -> float:
    if analyse.score_sentiment is not None:
        return float(analyse.score_sentiment)
    return _SENTIMENT_SCORE_FALLBACK.get(analyse.sentiment, 0.0)


def _serialize(feedback: Feedback, analyse: AnalyseIA) -> dict[str, Any]:
    agence = feedback.qr_code.agence if feedback.qr_code else None
    contact = feedback.demande_contact
    data: dict[str, Any] = {
        "id": str(feedback.id),
        "note": feedback.note,
        "commentaire": feedback.commentaire,
        "date_soumission": feedback.date_soumission.isoformat(),
        "agence_nom": agence.nom if agence else None,
        "sentiment": analyse.sentiment.value,
        "sentiment_score": _sentiment_score(analyse),
        "theme_principal": analyse.theme_principal,
        "criticite": analyse.criticite.value,
        "necessite_verification": analyse.necessite_verification,
    }
    if contact and contact.telephone:
        data["contact_telephone"] = contact.telephone
    return data


def _query_feedbacks_analyses(db: Session, agence_id: Optional[UUID] = None):
    query = (
        db.query(Feedback, AnalyseIA)
        .join(AnalyseIA, AnalyseIA.feedback_id == Feedback.id)
        .options(
            joinedload(Feedback.qr_code).joinedload(QRCode.agence),
            joinedload(Feedback.demande_contact),
        )
    )
    if agence_id is not None:
        query = query.join(QRCode, Feedback.qr_code_id == QRCode.id).filter(QRCode.agence_id == agence_id)
    return query


def _get_feedbacks(db: Session, agence_id: Optional[UUID], jours: int) -> list[dict[str, Any]]:
    """Retourne les feedbacks (déjà analysés) des `jours` derniers jours, fusionnés avec leur analyse."""
    seuil = datetime.now(timezone.utc) - timedelta(days=jours)
    rows = (
        _query_feedbacks_analyses(db, agence_id)
        .filter(Feedback.date_soumission >= seuil)
        .all()
    )
    return [_serialize(fb, an) for fb, an in rows]


def _get_feedbacks_periode(
    db: Session, agence_id: Optional[UUID], date_debut: datetime, date_fin: datetime
) -> list[dict[str, Any]]:
    """Retourne les feedbacks (déjà analysés) strictement entre deux dates [date_debut, date_fin[."""
    rows = (
        _query_feedbacks_analyses(db, agence_id)
        .filter(Feedback.date_soumission >= date_debut, Feedback.date_soumission < date_fin)
        .all()
    )
    return [_serialize(fb, an) for fb, an in rows]


def query_alertes_critiques(
    db: Session, agence_id: Optional[UUID] = None, jours: int = 7
) -> list[dict[str, Any]]:
    """
    Retourne les feedbacks de criticité élevée ou critique, triés par
    score de priorité décroissant (pas juste par niveau brut).

    score_priorite = criticité (poids) + fraîcheur (plus récent = plus haut)
    + fréquence du thème sur la période (un thème qui revient souvent pèse
    plus qu'un cas isolé, même à criticité égale).
    """
    feedbacks = _get_feedbacks(db, agence_id, jours)
    alertes = [f for f in feedbacks if f["criticite"] in _CRITICITES_ALERTE]
    if not alertes:
        return []

    # Fréquence du thème sur l'ensemble de la période (pas seulement les alertes)
    freq_theme: dict[Any, int] = {}
    for f in feedbacks:
        freq_theme[f["theme_principal"]] = freq_theme.get(f["theme_principal"], 0) + 1
    freq_max = max(freq_theme.values()) if freq_theme else 1

    maintenant = datetime.now(timezone.utc)
    for f in alertes:
        date_fb = datetime.fromisoformat(f["date_soumission"])
        age_jours = max((maintenant - date_fb).days, 0)
        fraicheur = max(1 - (age_jours / max(jours, 1)), 0)  # 1 = aujourd'hui, 0 = en bout de période
        frequence_normalisee = freq_theme.get(f["theme_principal"], 1) / freq_max

        score = (
            0.5 * _POIDS_CRITICITE.get(f["criticite"], 0.5)
            + 0.3 * fraicheur
            + 0.2 * frequence_normalisee
        )
        f["score_priorite"] = round(score, 3)

    return sorted(alertes, key=lambda f: f["score_priorite"], reverse=True)


def query_statistiques_theme(
    db: Session, agence_id: Optional[UUID] = None, jours: int = 7
) -> dict[str, Any]:
    """Retourne la répartition des feedbacks par thème sur la période."""
    feedbacks = _get_feedbacks(db, agence_id, jours)
    par_theme: dict[Any, int] = {}
    for f in feedbacks:
        theme = f["theme_principal"]
        par_theme[theme] = par_theme.get(theme, 0) + 1
    return {"total": len(feedbacks), "par_theme": par_theme}


def query_a_verifier(
    db: Session, agence_id: Optional[UUID] = None, jours: int = 7
) -> list[dict[str, Any]]:
    """Retourne les feedbacks signalés à vérification manuelle (discordance note/commentaire, BF-08)."""
    feedbacks = _get_feedbacks(db, agence_id, jours)
    return [f for f in feedbacks if f.get("necessite_verification") is True]


def query_problemes_recurrents(
    db: Session, agence_id: Optional[UUID] = None, jours: int = 30
) -> list[dict[str, Any]]:
    """
    Regroupe les feedbacks par (agence, thème) et retourne les couples
    apparaissant au moins _SEUIL_RECURRENCE fois — un problème signalé une
    seule fois n'est pas "récurrent", c'est un incident isolé.
    """
    feedbacks = _get_feedbacks(db, agence_id, jours)
    groupes: dict[tuple[Any, Any], list[dict[str, Any]]] = {}
    for f in feedbacks:
        cle = (f["agence_nom"], f["theme_principal"])
        groupes.setdefault(cle, []).append(f)

    recurrents = []
    for (agence, theme), items in groupes.items():
        if len(items) >= _SEUIL_RECURRENCE:
            recurrents.append({
                "agence_nom": agence,
                "theme": theme,
                "occurrences": len(items),
                "criticite_max": max(items, key=lambda i: _POIDS_CRITICITE.get(i["criticite"], 0))["criticite"],
                "derniere_occurrence": max(i["date_soumission"] for i in items),
            })
    return sorted(recurrents, key=lambda r: r["occurrences"], reverse=True)


def comparer_periodes(
    db: Session, agence_id: Optional[UUID] = None, jours_periode: int = 7
) -> dict[str, Any]:
    """
    Compare la période actuelle (derniers `jours_periode` jours) à la
    période précédente de même durée. Détecte les anomalies = variation
    relative au-delà de _SEUIL_VARIATION_ANOMALIE sur le sentiment moyen,
    le taux de criticité, ou l'apparition/hausse forte d'un thème.

    Calcul 100% déterministe — le LLM ne fait que formuler le résultat.
    """
    maintenant = datetime.now(timezone.utc)
    debut_actuelle = maintenant - timedelta(days=jours_periode)
    debut_precedente = debut_actuelle - timedelta(days=jours_periode)

    actuelle = _get_feedbacks_periode(db, agence_id, debut_actuelle, maintenant)
    precedente = _get_feedbacks_periode(db, agence_id, debut_precedente, debut_actuelle)

    def _stats(feedbacks: list[dict[str, Any]]) -> dict[str, Any]:
        if not feedbacks:
            return {"total": 0, "sentiment_moyen": 0.0, "taux_criticite": 0.0, "par_theme": {}}
        sentiment_moyen = sum(f["sentiment_score"] for f in feedbacks) / len(feedbacks)
        taux_criticite = sum(1 for f in feedbacks if f["criticite"] in _CRITICITES_ALERTE) / len(feedbacks)
        par_theme: dict[Any, int] = {}
        for f in feedbacks:
            par_theme[f["theme_principal"]] = par_theme.get(f["theme_principal"], 0) + 1
        return {"total": len(feedbacks), "sentiment_moyen": round(sentiment_moyen, 3),
                "taux_criticite": round(taux_criticite, 3), "par_theme": par_theme}

    stats_actuelle = _stats(actuelle)
    stats_precedente = _stats(precedente)

    anomalies = []

    # Variation du sentiment moyen
    if stats_precedente["total"] > 0:
        delta_sentiment = stats_actuelle["sentiment_moyen"] - stats_precedente["sentiment_moyen"]
        if abs(delta_sentiment) >= _SEUIL_VARIATION_ANOMALIE:
            anomalies.append({
                "type": "sentiment",
                "description": f"Sentiment moyen {'en baisse' if delta_sentiment < 0 else 'en hausse'} "
                                f"de {abs(delta_sentiment):.2f} point(s)",
                "valeur_actuelle": stats_actuelle["sentiment_moyen"],
                "valeur_precedente": stats_precedente["sentiment_moyen"],
            })

    # Variation du taux de criticité
    if stats_precedente["total"] > 0:
        delta_criticite = stats_actuelle["taux_criticite"] - stats_precedente["taux_criticite"]
        if abs(delta_criticite) >= _SEUIL_VARIATION_ANOMALIE:
            anomalies.append({
                "type": "criticite",
                "description": f"Taux de feedbacks critiques/élevés {'en hausse' if delta_criticite > 0 else 'en baisse'} "
                                f"de {abs(delta_criticite) * 100:.0f} points de pourcentage",
                "valeur_actuelle": stats_actuelle["taux_criticite"],
                "valeur_precedente": stats_precedente["taux_criticite"],
            })

    # Thèmes nouveaux ou en forte hausse
    for theme, count_actuel in stats_actuelle["par_theme"].items():
        count_precedent = stats_precedente["par_theme"].get(theme, 0)
        if count_precedent == 0 and count_actuel >= 2:
            anomalies.append({
                "type": "theme_nouveau",
                "description": f"Thème '{theme}' absent la période précédente, "
                                f"{count_actuel} occurrence(s) cette période",
            })
        elif count_precedent > 0:
            variation = (count_actuel - count_precedent) / count_precedent
            if variation >= _SEUIL_VARIATION_ANOMALIE and count_actuel >= 2:
                anomalies.append({
                    "type": "theme_hausse",
                    "description": f"Thème '{theme}' en hausse de {variation * 100:.0f}% "
                                    f"({count_precedent} -> {count_actuel} occurrences)",
                })

    return {
        "periode_actuelle": stats_actuelle,
        "periode_precedente": stats_precedente,
        "anomalies": anomalies,
    }


def query_evolution_satisfaction(
    db: Session, agence_id: Optional[UUID] = None, jours_periode: int = 7, nb_periodes: int = 4
) -> list[dict[str, Any]]:
    """
    Retourne le sentiment moyen sur `nb_periodes` périodes consécutives de
    `jours_periode` jours chacune, de la plus ancienne à la plus récente —
    pour suivre l'évolution de la satisfaction dans le temps.
    """
    maintenant = datetime.now(timezone.utc)
    periodes = []
    for i in range(nb_periodes - 1, -1, -1):
        fin = maintenant - timedelta(days=jours_periode * i)
        debut = fin - timedelta(days=jours_periode)
        feedbacks = _get_feedbacks_periode(db, agence_id, debut, fin)
        sentiment_moyen = (
            round(sum(f["sentiment_score"] for f in feedbacks) / len(feedbacks), 3)
            if feedbacks else None
        )
        periodes.append({
            "periode": f"{debut.strftime('%Y-%m-%d')} au {fin.strftime('%Y-%m-%d')}",
            "nombre_feedbacks": len(feedbacks),
            "sentiment_moyen": sentiment_moyen,
        })
    return periodes
