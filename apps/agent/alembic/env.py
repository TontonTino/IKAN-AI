"""
Configuration Alembic — agent IA IKAN AI.

IMPORTANT : target_metadata pointe UNIQUEMENT sur app.db.session.Base, qui
ne porte que le modèle ActionAgent (table actions_agent). Les modèles
readonly (app/models/readonly.py) vivent sur un Base séparé
(ReadOnlyBase) volontairement JAMAIS importé ici — Alembic ne doit jamais
proposer de migration sur feedbacks/analyses_ia/agences/etc., ces tables
appartiennent au backend principal (apps/api), pas à ce service.
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import Base
from app.models import action_agent  # noqa — enregistre ActionAgent sur Base.metadata
from app.models import conversation  # noqa — enregistre Conversation/ConversationTurn sur Base.metadata
from app.config.settings import settings

config = context.config

db_url = settings.DATABASE_URL.strip()
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Filet de sécurité supplémentaire : même si une table étrangère finissait
# par apparaître dans target_metadata, on ne génère jamais de migration
# pour autre chose que actions_agent.
_TABLES_GEREES = {"actions_agent", "conversations", "conversation_turns"}


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table":
        return name in _TABLES_GEREES
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
