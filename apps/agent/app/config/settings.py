"""
Configuration centrale de l'agent IA IKAN AI — service FastAPI indépendant.
Charge les variables d'environnement depuis .env (voir .env.example).
"""
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"


class Settings(BaseSettings):
    # Application
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8001
    DEBUG: bool = True
    PROJECT_NAME: str = "IKAN AI — Agent"
    API_STR: str = ""

    # Base de données — même instance PostgreSQL que le backend principal (apps/api)
    DATABASE_URL: str

    # JWT — identiques au backend principal : l'agent VÉRIFIE les tokens émis
    # au login par apps/api, il n'en émet jamais lui-même.
    SECRET_KEY: str
    ALGORITHM: str = "HS256"

    # Secret partagé pour authentifier les appels webhook du backend principal
    WEBHOOK_SECRET: str

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:4321,http://localhost:5173"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    # Mistral — génération de texte (Q&A, brouillons d'action)
    MISTRAL_API_KEY: str = ""
    MISTRAL_MODEL: str = "mistral-small-latest"

    # Groq — provider actif pour la génération de texte (remplace Mistral)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "groq/compound-mini"

    # Hugging Face — réservé, non utilisé par le classifieur d'intention actuel
    # (moteur à mots-clés déterministe, voir app/agent/intent_classifier.py).
    HF_API_KEY: str = ""

    # WhatsApp Business (Meta Cloud API)
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_TEMPLATE_NAME: str = "suivi_reclamation_client"
    WHATSAPP_TEMPLATE_LANG: str = "fr"

    class Config:
        env_file = (str(ENV_PATH), ".env")
        case_sensitive = True


settings = Settings()
