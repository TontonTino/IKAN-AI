"""
Fonctions de requête — une par intention. CONVERTI depuis le prototype
(mock_store en mémoire) vers de vraies requêtes SQLAlchemy sur la base
PostgreSQL partagée avec le backend principal.

Ces fonctions n'appellent jamais le LLM et ne renvoient jamais de données
inventées : seulement ce qui est réellement en base. Toute détection de
tendance/anomalie/priorité est un calcul statistique déterministe — jamais
une estimation du LLM (règle architecturale n°5 du prototype, conservée).

NOTE — necessite_verification : ce champ n'existe pas dans le modèle
AnalyseIA réel du backend principal (vérifié : absent du modèle SQLAlchemy
et de la migration Alembic initiale). Il est donc DÉRIVÉ ici de
`discordance_detectee` (note client haute mais commentaire négatif) — le
signal le plus proche qui existe réellement en base et qui correspond
conceptuellement à "ce feedback mérite un second regard humain". Si le
backend principal ajoute un jour une vraie colonne necessite_verification,
remplacer cette dérivation dans `_ligne_vers_dict()` ci-dessous.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.readonly import Feedback, AnalyseIA, Agence, QRCode, DemandeContact

_CRITICITES_ALERTE = {"elevee", "critique"}

_POIDS_CRITICITE = {"faible": 0.1, "moyenne": 0.4, "elevee": 0.7, "critique": 1.0}
_SEUIL_RECURRENCE = 2
_SEUIL_VARIATION_ANOMALIE = 0.3

# Seuils pour query_predictions() — voir docstring de la fonction.
_SEUIL_HAUSSE_RISQUE = 0.3
_SEUIL_CRITICITE_RISQUE = 0.4
_SEUIL_BAISSE_OPPORTUNITE = 0.2
_SEUIL_CRITICITE_HAUTE_PRECEDENTE = 0.5
_SEUIL_CRITICITE_BASSE_ACTUELLE = 0.3
_MIN_FEEDBACKS_PERIODE = 5
_MIN_CAS_CRITIQUES_NOUVEAU_THEME = 2


def _ligne_vers_dict(
    feedback: Feedback, analyse: AnalyseIA, agence: Agence, demande: DemandeContact | None
) -> dict[str, Any]:
    return {
        "id": str(feedback.id),
        "note": feedback.note,
        "commentaire": feedback.commentaire or "",
        "date_soumission": feedback.date_soumission.isoformat(),
        "agence_id": str(agence.id),
        "agence_nom": agence.nom,
        # présumé = numéro WhatsApp (voir GUIDE_INTEGRATION.md)
        "contact_telephone": demande.telephone if demande else None,
        "sentiment": analyse.sentiment.value,
        "sentiment_score": analyse.score_sentiment if analyse.score_sentiment is not None else 0.5,
        "theme_principal": analyse.theme_principal or "autre",
        "criticite": analyse.criticite.value,
        # Dérivé de discordance_detectee — voir note de module ci-dessus.
        "necessite_verification": bool(analyse.discordance_detectee),
    }


def _requete_feedbacks(
    db: Session, agence_id: Optional[uuid.UUID], date_debut: datetime, date_fin: datetime
) -> list[dict[str, Any]]:
    """
    Reproduit mock_store.get_feedbacks_periode() : jointure
    Feedback -> AnalyseIA (inner — un feedback sans analyse n'est pas
    exploitable par l'agent) -> QRCode -> Agence, + outer join
    DemandeContact pour le numéro de téléphone.
    """
    query = (
        db.query(Feedback, AnalyseIA, Agence, DemandeContact)
        .join(AnalyseIA, AnalyseIA.feedback_id == Feedback.id)
        .join(QRCode, Feedback.qr_code_id == QRCode.id)
        .join(Agence, QRCode.agence_id == Agence.id)
        .outerjoin(DemandeContact, DemandeContact.feedback_id == Feedback.id)
        .filter(Feedback.date_soumission >= date_debut, Feedback.date_soumission < date_fin)
    )
    if agence_id is not None:
        query = query.filter(Agence.id == agence_id)

    return [
        _ligne_vers_dict(feedback, analyse, agence, demande)
        for feedback, analyse, agence, demande in query.all()
    ]


def get_feedbacks(
    db: Session, agence_id: Optional[uuid.UUID] = None, jours: int = 7
) -> list[dict[str, Any]]:
    """Équivalent mock_store.get_feedbacks() : derniers `jours` jours depuis maintenant."""
    maintenant = datetime.now(timezone.utc)
    return _requete_feedbacks(db, agence_id, maintenant - timedelta(days=jours), maintenant)


def get_feedback_with_analyse(db: Session, feedback_id: uuid.UUID) -> Optional[dict[str, Any]]:
    """Équivalent mock_store.get_analyse(feedback_id) : un seul feedback + son analyse."""
    row = (
        db.query(Feedback, AnalyseIA, Agence, DemandeContact)
        .join(AnalyseIA, AnalyseIA.feedback_id == Feedback.id)
        .join(QRCode, Feedback.qr_code_id == QRCode.id)
        .join(Agence, QRCode.agence_id == Agence.id)
        .outerjoin(DemandeContact, DemandeContact.feedback_id == Feedback.id)
        .filter(Feedback.id == feedback_id)
        .first()
    )
    if row is None:
        return None
    feedback, analyse, agence, demande = row
    return _ligne_vers_dict(feedback, analyse, agence, demande)


def query_alertes_critiques(
    db: Session, agence_id: Optional[uuid.UUID] = None, jours: int = 7
) -> list[dict[str, Any]]:
    """
    Retourne les feedbacks de criticité élevée ou critique, triés par
    score de priorité décroissant (criticité + fraîcheur + fréquence du thème).
    """
    feedbacks = get_feedbacks(db, agence_id=agence_id, jours=jours)
    alertes = [f for f in feedbacks if f["criticite"] in _CRITICITES_ALERTE]
    if not alertes:
        return []

    freq_theme: dict[str, int] = {}
    for f in feedbacks:
        freq_theme[f["theme_principal"]] = freq_theme.get(f["theme_principal"], 0) + 1
    freq_max = max(freq_theme.values()) if freq_theme else 1

    maintenant = datetime.now(timezone.utc)
    for f in alertes:
        date_fb = datetime.fromisoformat(f["date_soumission"])
        age_jours = max((maintenant - date_fb).days, 0)
        fraicheur = max(1 - (age_jours / max(jours, 1)), 0)
        frequence_normalisee = freq_theme.get(f["theme_principal"], 1) / freq_max

        score = (
            0.5 * _POIDS_CRITICITE.get(f["criticite"], 0.5)
            + 0.3 * fraicheur
            + 0.2 * frequence_normalisee
        )
        f["score_priorite"] = round(score, 3)

    return sorted(alertes, key=lambda f: f["score_priorite"], reverse=True)


def query_statistiques_theme(
    db: Session, agence_id: Optional[uuid.UUID] = None, jours: int = 7
) -> dict[str, Any]:
    """Retourne la répartition des feedbacks par thème sur la période."""
    feedbacks = get_feedbacks(db, agence_id=agence_id, jours=jours)
    par_theme: dict[str, int] = {}
    for f in feedbacks:
        theme = f["theme_principal"]
        par_theme[theme] = par_theme.get(theme, 0) + 1
    return {"total": len(feedbacks), "par_theme": par_theme}


def query_a_verifier(
    db: Session, agence_id: Optional[uuid.UUID] = None, jours: int = 7
) -> list[dict[str, Any]]:
    """Retourne les feedbacks signalés à vérification manuelle (voir note de module)."""
    feedbacks = get_feedbacks(db, agence_id=agence_id, jours=jours)
    return [f for f in feedbacks if f.get("necessite_verification") is True]


def query_problemes_recurrents(
    db: Session, agence_id: Optional[uuid.UUID] = None, jours: int = 30
) -> list[dict[str, Any]]:
    """
    Regroupe les feedbacks par (agence, thème) et retourne les couples
    apparaissant au moins _SEUIL_RECURRENCE fois.
    """
    feedbacks = get_feedbacks(db, agence_id=agence_id, jours=jours)
    groupes: dict[tuple[str, str], list[dict[str, Any]]] = {}
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
    db: Session, agence_id: Optional[uuid.UUID] = None, jours_periode: int = 7
) -> dict[str, Any]:
    """
    Compare la période actuelle à la période précédente de même durée.
    Détecte les anomalies = variation relative au-delà de
    _SEUIL_VARIATION_ANOMALIE sur le sentiment moyen, le taux de criticité,
    ou l'apparition/hausse forte d'un thème. Calcul 100% déterministe.
    """
    maintenant = datetime.now(timezone.utc)
    debut_actuelle = maintenant - timedelta(days=jours_periode)
    debut_precedente = debut_actuelle - timedelta(days=jours_periode)

    actuelle = _requete_feedbacks(db, agence_id, debut_actuelle, maintenant)
    precedente = _requete_feedbacks(db, agence_id, debut_precedente, debut_actuelle)

    def _stats(feedbacks: list[dict[str, Any]]) -> dict[str, Any]:
        if not feedbacks:
            return {"total": 0, "sentiment_moyen": 0.0, "taux_criticite": 0.0, "par_theme": {}}
        sentiment_moyen = sum(f["sentiment_score"] for f in feedbacks) / len(feedbacks)
        taux_criticite = sum(1 for f in feedbacks if f["criticite"] in _CRITICITES_ALERTE) / len(feedbacks)
        par_theme: dict[str, int] = {}
        for f in feedbacks:
            par_theme[f["theme_principal"]] = par_theme.get(f["theme_principal"], 0) + 1
        return {"total": len(feedbacks), "sentiment_moyen": round(sentiment_moyen, 3),
                "taux_criticite": round(taux_criticite, 3), "par_theme": par_theme}

    stats_actuelle = _stats(actuelle)
    stats_precedente = _stats(precedente)

    anomalies = []

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
    db: Session,
    agence_id: Optional[uuid.UUID] = None,
    jours_periode: int = 7,
    nb_periodes: int = 4,
) -> list[dict[str, Any]]:
    """
    Retourne le sentiment moyen sur `nb_periodes` périodes consécutives de
    `jours_periode` jours chacune, de la plus ancienne à la plus récente.
    """
    maintenant = datetime.now(timezone.utc)
    periodes = []
    for i in range(nb_periodes - 1, -1, -1):
        fin = maintenant - timedelta(days=jours_periode * i)
        debut = fin - timedelta(days=jours_periode)
        feedbacks = _requete_feedbacks(db, agence_id, debut, fin)
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


def _stats_par_theme(feedbacks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Retourne {theme: {"total": n, "critiques_eleves": n, "taux_criticite": float}}."""
    stats: dict[str, dict[str, Any]] = {}
    for f in feedbacks:
        theme = f["theme_principal"]
        s = stats.setdefault(theme, {"total": 0, "critiques_eleves": 0})
        s["total"] += 1
        if f["criticite"] in _CRITICITES_ALERTE:
            s["critiques_eleves"] += 1
    for s in stats.values():
        s["taux_criticite"] = round(s["critiques_eleves"] / s["total"], 3) if s["total"] else 0.0
    return stats


def query_predictions(
    db: Session, agence_id: Optional[uuid.UUID] = None, jours_periode: int = 7
) -> dict[str, Any]:
    """
    Traduit une comparaison de périodes en signaux "risque" / "opportunité"
    compréhensibles par un manager — jamais le LLM qui décide, uniquement
    des règles déterministes appliquées ici.

    ÉCART assumé par rapport à la demande initiale ("appelle
    comparer_periodes() puis interprète") : comparer_periodes() ne retourne,
    pour `par_theme`, que des COMPTAGES d'occurrences par thème (pas de
    ventilation par criticité). Or les règles ci-dessous ont besoin, PAR
    THÈME, du taux de criticité de chaque période (ex. "taux de criticité
    actuel dépasse 40 %") — une donnée que comparer_periodes() ne calcule
    pas et ne peut pas être étendue pour fournir sans changer sa signature
    ou son comportement pour l'intention "tendances_anomalies" qui
    l'utilise déjà (hors périmètre de cette tâche : "ne touche à rien
    d'autre"). Cette fonction appelle donc directement `_requete_feedbacks()`
    pour les deux mêmes périodes que comparer_periodes() (période actuelle
    de `jours_periode` jours, période précédente de même durée juste avant),
    et calcule elle-même les statistiques par thème via `_stats_par_theme()`.
    comparer_periodes() n'est ni modifiée ni appelée par cette fonction.

    Règles (déterministes, appliquées thème par thème) :

    RISQUES :
      - occurrences en hausse de plus de 30 % ET taux de criticité actuel
        du thème > 40 %  → urgence "haute" si taux >= 60 % ou hausse > 60 %,
        sinon "moyenne"
      - thème absent la période précédente, apparu avec >= 2 cas
        critiques/élevés cette période → urgence "haute" si >= 3 cas,
        sinon "moyenne"

    OPPORTUNITÉS :
      - occurrences en baisse de plus de 20 %
      - ou taux de criticité passé de > 50 % (période précédente) à
        < 30 % (période actuelle)

    `donnees_insuffisantes` est à True si l'une des deux périodes contient
    moins de 5 feedbacks — dans ce cas `risques` et `opportunites` sont
    retournés vides plutôt que calculés sur un échantillon non significatif.
    """
    maintenant = datetime.now(timezone.utc)
    debut_actuelle = maintenant - timedelta(days=jours_periode)
    debut_precedente = debut_actuelle - timedelta(days=jours_periode)

    actuelle = _requete_feedbacks(db, agence_id, debut_actuelle, maintenant)
    precedente = _requete_feedbacks(db, agence_id, debut_precedente, debut_actuelle)

    periode_analysee = (
        f"actuelle : {debut_actuelle.strftime('%Y-%m-%d')} au {maintenant.strftime('%Y-%m-%d')} "
        f"| précédente : {debut_precedente.strftime('%Y-%m-%d')} au {debut_actuelle.strftime('%Y-%m-%d')}"
    )

    if len(actuelle) < _MIN_FEEDBACKS_PERIODE or len(precedente) < _MIN_FEEDBACKS_PERIODE:
        return {
            "risques": [],
            "opportunites": [],
            "periode_analysee": periode_analysee,
            "donnees_insuffisantes": True,
        }

    stats_actuelle = _stats_par_theme(actuelle)
    stats_precedente = _stats_par_theme(precedente)

    risques: list[dict[str, Any]] = []
    opportunites: list[dict[str, Any]] = []

    for theme in set(stats_actuelle) | set(stats_precedente):
        actuel = stats_actuelle.get(theme)
        precedent = stats_precedente.get(theme)

        count_actuel = actuel["total"] if actuel else 0
        count_precedent = precedent["total"] if precedent else 0
        taux_actuel = actuel["taux_criticite"] if actuel else 0.0
        taux_precedent = precedent["taux_criticite"] if precedent else 0.0

        if precedent is not None and count_precedent > 0 and actuel is not None:
            variation = (count_actuel - count_precedent) / count_precedent
            if variation > _SEUIL_HAUSSE_RISQUE and taux_actuel > _SEUIL_CRITICITE_RISQUE:
                risques.append({
                    "theme": theme,
                    "signal": (
                        f"Occurrences en hausse de {variation * 100:.0f}% "
                        f"({count_precedent} -> {count_actuel}), avec {taux_actuel * 100:.0f}% "
                        f"de cas critiques/élevés sur la période actuelle"
                    ),
                    "urgence": "haute" if (taux_actuel >= 0.6 or variation > 0.6) else "moyenne",
                })
        elif precedent is None and actuel is not None:
            cas_critiques = actuel["critiques_eleves"]
            if cas_critiques >= _MIN_CAS_CRITIQUES_NOUVEAU_THEME:
                risques.append({
                    "theme": theme,
                    "signal": (
                        f"Thème absent de la période précédente, apparaît avec {count_actuel} "
                        f"cas dont {cas_critiques} critique(s)/élevé(s)"
                    ),
                    "urgence": "haute" if cas_critiques >= 3 else "moyenne",
                })

        if precedent is not None and count_precedent > 0 and actuel is not None and count_actuel > 0:
            variation = (count_actuel - count_precedent) / count_precedent
            if variation < -_SEUIL_BAISSE_OPPORTUNITE:
                opportunites.append({
                    "theme": theme,
                    "signal": (
                        f"Occurrences en baisse de {abs(variation) * 100:.0f}% "
                        f"({count_precedent} -> {count_actuel})"
                    ),
                })
            elif (
                taux_precedent > _SEUIL_CRITICITE_HAUTE_PRECEDENTE
                and taux_actuel < _SEUIL_CRITICITE_BASSE_ACTUELLE
            ):
                opportunites.append({
                    "theme": theme,
                    "signal": (
                        f"Taux de criticité en forte baisse : {taux_precedent * 100:.0f}% "
                        f"-> {taux_actuel * 100:.0f}%"
                    ),
                })

    risques.sort(key=lambda r: (r["urgence"] != "haute", r["theme"]))
    opportunites.sort(key=lambda o: o["theme"])

    return {
        "risques": risques,
        "opportunites": opportunites,
        "periode_analysee": periode_analysee,
        "donnees_insuffisantes": False,
    }


_NB_ALERTES_PRIORITAIRES_MAX = 5


def _tendance_globale(comparaison: dict[str, Any]) -> str:
    """
    Dérive une tendance globale unique ("degradation"/"amelioration"/
    "stable"/"insuffisant") à partir de comparer_periodes().

    Aucune des fonctions existantes ne retourne directement une "tendance
    globale" : celle-ci est déduite ici des anomalies de type "sentiment"
    et "criticite" déjà calculées par comparer_periodes() (mêmes seuils
    déterministes que l'intention "tendances_anomalies", pas de nouveau
    seuil inventé). Si la période précédente n'a aucun feedback, la
    comparaison n'a pas de sens -> "insuffisant". Si les deux périodes ont
    des feedbacks mais qu'aucune anomalie sentiment/criticité n'est
    détectée -> "stable". Si les signaux sentiment et criticité se
    contredisent (rare) -> "stable" par prudence, plutôt que de trancher.
    """
    if comparaison["periode_precedente"]["total"] == 0:
        return "insuffisant"

    degrade = False
    ameliore = False
    for anomalie in comparaison["anomalies"]:
        if anomalie["type"] == "sentiment":
            if anomalie["valeur_actuelle"] < anomalie["valeur_precedente"]:
                degrade = True
            else:
                ameliore = True
        elif anomalie["type"] == "criticite":
            if anomalie["valeur_actuelle"] > anomalie["valeur_precedente"]:
                degrade = True
            else:
                ameliore = True

    if degrade and not ameliore:
        return "degradation"
    if ameliore and not degrade:
        return "amelioration"
    return "stable"


def query_recommandations(
    db: Session, agence_id: Optional[uuid.UUID] = None, jours: int = 7
) -> dict[str, Any]:
    """
    Agrège les sorties des autres fonctions de requête (jamais le LLM) pour
    produire la base factuelle d'un plan d'action priorisé. Voir
    qa_service.repondre_question() pour la mise en forme LLM de ces données.
    """
    alertes = query_alertes_critiques(db, agence_id=agence_id, jours=jours)
    problemes = query_problemes_recurrents(db, agence_id=agence_id, jours=jours)
    predictions = query_predictions(db, agence_id=agence_id, jours_periode=jours)
    comparaison = comparer_periodes(db, agence_id=agence_id, jours_periode=jours)

    alertes_prioritaires = [
        {
            "agence_nom": f["agence_nom"],
            "theme": f["theme_principal"],
            "criticite": f["criticite"],
            "score_priorite": f["score_priorite"],
            "commentaire_exemple": f["commentaire"],
        }
        for f in alertes[:_NB_ALERTES_PRIORITAIRES_MAX]
    ]

    problemes_systemiques = [
        {
            "agence_nom": p["agence_nom"],
            "theme": p["theme"],
            "occurrences": p["occurrences"],
            "criticite_max": p["criticite_max"],
        }
        for p in problemes
    ]

    risques_detectes = [
        {"theme": r["theme"], "signal": r["signal"], "urgence": r["urgence"]}
        for r in predictions["risques"]
    ]

    return {
        "alertes_prioritaires": alertes_prioritaires,
        "problemes_systemiques": problemes_systemiques,
        "risques_detectes": risques_detectes,
        "tendance_globale": _tendance_globale(comparaison),
        "periode_analysee": predictions["periode_analysee"],
        "donnees_disponibles": bool(alertes_prioritaires or problemes_systemiques or risques_detectes),
    }
