"""
Configuration centrale de l'application IKAN AI.
Charge les variables d'environnement depuis le fichier .env
"""
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl
from typing import List


from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"


class Settings(BaseSettings):
    # Application
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = True
    PROJECT_NAME: str = "IKAN AI"
    API_V1_STR: str = "/api/v1"

    # URL du formulaire client public (ex: pour la génération du QR code)
    PUBLIC_CLIENT_URL: str = "http://localhost:4321"

    # Base de données
    DATABASE_URL: str = "postgresql://ikanai_user:jBt03ZigY2of1Ucd0YxZVzWLnSEUlvmf@dpg-d9tej2h42hec7381j2ag-a.frankfurt-postgres.render.com/ikanai"

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:4321,http://localhost:5173,http://localhost:3000,http://127.0.0.1:4321,http://127.0.0.1:5173,https://ikanai-client.onrender.com,https://ikanai-dashboard.onrender.com"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    # Email (optionnel — pour les alertes)
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM: str = "noreply@ikanai.app"
    MAIL_PORT: int = 587
    MAIL_SERVER: str = "smtp.gmail.com"
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False

    # Agent IA — génération de brouillons (Mistral)
    MISTRAL_API_KEY: str = ""
    MISTRAL_MODEL: str = "mistral-small-latest"

    # NLP — authentification HuggingFace (téléchargement de modèles)
    HF_API_KEY: str = ""

    # Agent IA — classification d'intention Q&A (Hugging Face Inference API,
    # distinct du modèle local de thème/sentiment feedback)
    HF_SENTIMENT_MODEL: str = "cardiffnlp/twitter-xlm-roberta-base-sentiment-multilingual"
    HF_ZERO_SHOT_MODEL: str = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"

    # Agent IA — WhatsApp Business (Meta Cloud API)
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_TEMPLATE_NAME: str = "suivi_reclamation_client"
    WHATSAPP_TEMPLATE_LANG: str = "fr"

    class Config:
        env_file = (str(ENV_PATH), ".env", "apps/api/.env")
        case_sensitive = True


settings = Settings()
