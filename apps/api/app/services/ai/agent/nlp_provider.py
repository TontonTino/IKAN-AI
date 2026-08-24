"""
Client pour les modèles NLP légers hébergés sur Hugging Face Inference.

Porté depuis le prototype (Agent IA/app/providers/nlp_provider.py). Ce
module est le SEUL point de contact avec les endpoints HF pour la
classification d'intention. Il ne fait aucune interprétation
"intelligente" : il appelle le modèle et normalise la réponse brute dans
un format Python simple et prévisible pour le reste de l'application (voir
intent_classifier.py qui consomme classify_topk).

Le LLM (Mistral) n'intervient jamais ici : la classification d'intention
est assurée par un modèle déterministe et léger, conformément à la règle
architecturale n°1 du projet. Distinct de app.services.ai.classification_service
(thème/sentiment du feedback client, modèle local de l'équipe IA) : ici on
classe l'INTENTION de la question du manager.
"""

from __future__ import annotations

from typing import Any

import requests

from app.core.config import settings

HF_BASE_URL = "https://router.huggingface.co/hf-inference/models"


class NLPProviderError(RuntimeError):
    """Erreur levée pour tout problème d'appel au provider NLP."""


def _ensure_api_key() -> None:
    if not settings.HF_API_KEY:
        raise NLPProviderError(
            "HF_API_KEY est vide. Renseigne cette clé dans le fichier .env "
            "avant d'appeler le provider NLP."
        )


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.HF_API_KEY}",
        "Content-Type": "application/json",
    }


def _post(model: str, payload: dict[str, Any]) -> Any:
    _ensure_api_key()
    url = f"{HF_BASE_URL}/{model}"
    response = requests.post(url, headers=_headers(), json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def analyze_sentiment_raw(text: str) -> dict[str, Any]:
    """
    Analyse le sentiment d'un texte.

    ATTENTION au format réel de réponse HF pour ce type de modèle : c'est
    une LISTE DE LISTES, ex. [[{"label": "positive", "score": 0.8}, ...]].
    On prend la première liste interne, puis le label avec le score le
    plus élevé.

    Retourne {'label': 'positif'|'negatif'|'neutre', 'score': float}
    où score est signé dans [-1, 1] (positif > 0, négatif < 0).
    """
    raw = _post(settings.HF_SENTIMENT_MODEL, {"inputs": text})

    if not isinstance(raw, list) or not raw or not isinstance(raw[0], list):
        raise NLPProviderError(
            f"Format de réponse HF sentiment inattendu : {raw!r}"
        )

    candidates: list[dict[str, Any]] = raw[0]
    best = max(candidates, key=lambda c: c["score"])

    label_map = {
        "positive": "positif",
        "negative": "negatif",
        "neutral": "neutre",
        "positif": "positif",
        "negatif": "negatif",
        "neutre": "neutre",
    }
    label = label_map.get(str(best["label"]).lower(), "neutre")

    score = float(best["score"])
    if label == "negatif":
        score = -abs(score)
    elif label == "neutre":
        score = 0.0
    else:
        score = abs(score)

    return {"label": label, "score": score}


def classify_topk(
    text: str, candidate_labels: list[str], k: int = 2
) -> list[dict[str, Any]]:
    """
    Classification zero-shot d'un texte parmi une liste de labels candidats.

    ATTENTION : le endpoint zero-shot renvoie normalement une LISTE PLATE
    [{"label": ..., "score": ...}, ...] déjà triée par score décroissant
    (format actuel réel de l'API HF router). On gère malgré tout, par
    prudence, l'ancien format dict {"labels": [...], "scores": [...]} au
    cas où le endpoint appelé renverrait ce format legacy.

    Retourne une liste de {'label': str, 'score': float} triée décroissant,
    tronquée à k éléments.
    """
    if not text or not text.strip():
        return []

    payload = {
        "inputs": text,
        "parameters": {"candidate_labels": candidate_labels},
    }
    raw = _post(settings.HF_ZERO_SHOT_MODEL, payload)

    results: list[dict[str, Any]]

    if isinstance(raw, list):
        # Format actuel réel : liste plate de {"label":..., "score":...}
        results = [
            {"label": item["label"], "score": float(item["score"])} for item in raw
        ]
    elif isinstance(raw, dict) and "labels" in raw and "scores" in raw:
        # Format legacy, géré par prudence.
        results = [
            {"label": label, "score": float(score)}
            for label, score in zip(raw["labels"], raw["scores"])
        ]
    else:
        raise NLPProviderError(
            f"Format de réponse HF zero-shot inattendu : {raw!r}"
        )

    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:k]
