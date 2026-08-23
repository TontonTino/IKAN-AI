"""
Client pour l'API WhatsApp Business (Meta Cloud API).

Porté depuis le prototype (Agent IA/app/providers/whatsapp_provider.py).

CONTRAINTE NON CONTOURNABLE : WhatsApp interdit l'envoi d'un message libre
à un numéro qui ne vous a pas écrit dans les 24h précédentes ("customer
service window"). Comme le client contacte IKANAI via un formulaire web
(QR code) et non via WhatsApp, cette fenêtre n'est jamais ouverte pour un
premier contact — TOUT envoi doit donc passer par un "message template"
pré-approuvé par Meta, jamais par du texte libre envoyé directement.

Le contenu généré par l'agent (Mistral) vient remplir la ou les variables
du template, il ne remplace pas le template lui-même.

Documentation officielle : https://developers.facebook.com/docs/whatsapp/cloud-api
"""
from __future__ import annotations

from typing import Any

import requests

from app.core.config import settings

_API_VERSION = "v21.0"


class WhatsAppProviderError(RuntimeError):
    """Erreur levée pour tout problème d'envoi WhatsApp."""


def _ensure_config() -> None:
    manquants = []
    if not settings.WHATSAPP_ACCESS_TOKEN:
        manquants.append("WHATSAPP_ACCESS_TOKEN")
    if not settings.WHATSAPP_PHONE_NUMBER_ID:
        manquants.append("WHATSAPP_PHONE_NUMBER_ID")
    if manquants:
        raise WhatsAppProviderError(
            f"Configuration WhatsApp incomplète : {', '.join(manquants)} "
            f"manquant(s) dans .env. Voir le guide de configuration du "
            f"compte WhatsApp Business avant de pouvoir envoyer un message."
        )


def _normaliser_numero(numero: str) -> str:
    """L'API attend un numéro au format international SANS le '+'."""
    return numero.strip().lstrip("+").replace(" ", "")


def envoyer_message_template(
    numero_destinataire: str,
    nom_template: str,
    code_langue: str,
    parametres_corps: list[str],
) -> dict[str, Any]:
    """
    Envoie un message WhatsApp via un template pré-approuvé.

    Args:
        numero_destinataire: numéro du client, avec ou sans '+' (format international).
        nom_template: nom exact du template tel qu'approuvé dans Meta Business Manager.
        code_langue: ex. "fr" — doit correspondre à la langue du template approuvé.
        parametres_corps: valeurs à insérer dans les variables {{1}}, {{2}}, ...
            du corps du template, DANS L'ORDRE.

    Returns:
        La réponse brute de l'API Meta (contient notamment l'id du message envoyé).

    Raises:
        WhatsAppProviderError si la config est incomplète ou si l'envoi échoue.
    """
    _ensure_config()

    url = f"https://graph.facebook.com/{_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": _normaliser_numero(numero_destinataire),
        "type": "template",
        "template": {
            "name": nom_template,
            "language": {"code": code_langue},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in parametres_corps],
                }
            ] if parametres_corps else [],
        },
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code != 200:
        raise WhatsAppProviderError(
            f"Échec envoi WhatsApp (HTTP {response.status_code}) : {response.text}"
        )
    return response.json()
