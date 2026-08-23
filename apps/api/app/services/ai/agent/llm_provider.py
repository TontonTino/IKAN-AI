"""
Client pour l'API de complétion de chat Mistral.

Porté depuis le prototype (Agent IA/app/providers/llm_provider.py). Ce
provider est délibérément minimal et ne fait qu'une chose : envoyer un
prompt système + un prompt utilisateur et retourner le texte généré. Il ne
prend AUCUNE décision de routage ou de logique métier — la classification
(sentiment/thème) reste entièrement gérée par app.services.ai.classification_service,
jamais par ce module.
"""
from __future__ import annotations

import requests

from app.core.config import settings

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"


class LLMProviderError(RuntimeError):
    """Erreur levée pour tout problème d'appel au provider LLM."""


def _ensure_api_key() -> None:
    if not settings.MISTRAL_API_KEY:
        raise LLMProviderError(
            "MISTRAL_API_KEY est vide. Renseigne cette clé dans le fichier "
            ".env avant d'appeler le provider LLM."
        )


def generate_text(system_prompt: str, user_prompt: str, max_tokens: int = 400) -> str:
    """Appelle Mistral et retourne le texte de la réponse générée."""
    _ensure_api_key()

    headers = {
        "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.MISTRAL_MODEL,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    response = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMProviderError(
            f"Format de réponse Mistral inattendu : {data!r}"
        ) from exc
