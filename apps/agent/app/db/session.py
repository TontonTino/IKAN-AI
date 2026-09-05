"""
Connexion SQLAlchemy — MÊME base PostgreSQL que le backend principal (apps/api).

`Base` ici ne porte QUE le modèle en écriture de l'agent (ActionAgent,
table `actions_agent`). Les modèles en lecture seule des tables du backend
principal (app/models/readonly.py) sont mappés sur un Base séparé
(ReadOnlyBase) afin qu'Alembic, dont la target_metadata pointe sur
`Base.metadata`, ne gère jamais ces tables : l'agent ne les crée ni ne les
modifie, il se contente de les lire.
"""
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from fastapi import HTTPException, status

from app.config.settings import settings

logger = logging.getLogger(__name__)

db_url = settings.DATABASE_URL.strip()
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# sslmode=require systématique sur les bases distantes (ex: Render PostgreSQL)
if "localhost" not in db_url and "127.0.0.1" not in db_url and "sslmode" not in db_url:
    separator = "&" if "?" in db_url else "?"
    db_url = f"{db_url}{separator}sslmode=require"

engine = create_engine(
    db_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base des modèles EN ÉCRITURE de l'agent (uniquement ActionAgent)."""
    pass


def get_db():
    """Dépendance FastAPI : fournit une session de base de données sécurisée."""
    db = None
    try:
        db = SessionLocal()
        yield db
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DB CONNECTION ERROR] {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur de connexion PostgreSQL: {str(e)}",
        )
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
