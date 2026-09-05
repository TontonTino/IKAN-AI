"""
Classification d'intention — SEUL point d'entrée pour interpréter une
question en langage naturel.

Conformément à la règle architecturale n°1 du projet, c'est ce module
(et non le LLM) qui décide quelle fonction de requête appeler.

Routage déterministe par mots-clés (PAS de zero-shot ici) : sur un jeu
fermé de 8 intentions connues, un modèle NLI zero-shot generique s'est
avéré peu fiable (confusions entre intentions proches, et une intention
qui capturait des questions hors périmètre au lieu de "autre" — voir
historique du correctif). Ce module est distinct de
app.services.ai.classification_service, qui classe le THÈME des
commentaires clients et reste sur un modèle zero-shot/fine-tuné, non
concerné par ce changement.

Règle n°2 : "autre" est le comportement par défaut (garde-fou), pas une
exception — retourné dès qu'aucun mot-clé ne matche.
"""

from __future__ import annotations

import unicodedata

# Ordre de priorité : du plus spécifique au plus général. La première
# intention dont un mot-clé matche la question normalisée est retournée.
_KEYWORDS: dict[str, list[str]] = {
    "alertes_critiques": ["alerte", "critique", "urgent", "urgence", "prioritaire"],
    "a_verifier": ["verifier", "verification", "a verifier"],
    "problemes_recurrents": [
        "recurrent", "revient", "reviennent", "souvent", "repete", "repetent",
    ],
    "tendances_anomalies": [
        "tendance", "anomalie", "change", "changement",
        "evolue par rapport", "vs la semaine",
    ],
    "evolution_satisfaction": [
        "evolution", "satisfaction", "dans le temps", "au fil du temps",
        "ameliore", "amelior",
    ],
    "statistiques_theme": ["repartition", "statistique", "par theme"],
    "resume_periode": ["resume", "synthese", "activite recente"],
    "predictions_risques": [
        "predire", "prediction", "anticiper", "risque",
        "va empirer", "va s ameliorer", "tendance future", "prochain mois",
        "futur", "avenir", "bientot", "craindre", "si ca continue",
        "potentiel", "probable",
    ],
}


def _normalize(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def classifier_intention(question: str) -> str:
    """
    Détermine l'intention d'une question en langage naturel par
    détection de mots-clés (accents et casse ignorés).

    Retourne "autre" si le texte est vide ou si aucun mot-clé ne matche.
    """
    if not question or not question.strip():
        return "autre"

    normalized = _normalize(question)

    for intention, keywords in _KEYWORDS.items():
        for keyword in keywords:
            if keyword in normalized:
                return intention

    return "autre"
