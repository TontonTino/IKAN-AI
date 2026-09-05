"""
Client pour l'API de complétion de chat — Groq (llama-3.1-8b-instant).

Porté depuis le prototype (app/providers/llm_provider.py), inchangé dans sa
logique. Ce provider est délibérément minimal et ne fait qu'une chose :
envoyer un prompt système + un prompt utilisateur et retourner le texte
généré. Il ne prend AUCUNE décision de routage ou de logique métier — le
LLM ne reçoit jamais la question brute de l'utilisateur pour l'interpréter
librement, seulement des données déjà récupérées et mises en forme par les
couches supérieures (qa_service, action_service).
"""
from __future__ import annotations

import requests

from app.config.settings import settings

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Fallback Mistral (même format de requête/réponse, OpenAI-compatible) :
# MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"


class LLMProviderError(RuntimeError):
    """Erreur levée pour tout problème d'appel au provider LLM."""


def _ensure_api_key() -> None:
    if not settings.GROQ_API_KEY:
        raise LLMProviderError(
            "GROQ_API_KEY est vide. Renseigne cette clé dans le fichier "
            ".env avant d'appeler le provider LLM."
        )
    # Fallback Mistral :
    # if not settings.MISTRAL_API_KEY:
    #     raise LLMProviderError(
    #         "MISTRAL_API_KEY est vide. Renseigne cette clé dans le fichier "
    #         ".env avant d'appeler le provider LLM."
    #     )


def generate_text(system_prompt: str, user_prompt: str, max_tokens: int = 400) -> str:
    """Appelle Groq et retourne le texte de la réponse générée."""
    _ensure_api_key()

    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.GROQ_MODEL,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
    # Fallback Mistral :
    # response = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMProviderError(
            f"Format de réponse Groq inattendu : {data!r}"
        ) from exc
