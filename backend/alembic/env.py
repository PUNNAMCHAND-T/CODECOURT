"""Alembic environment configuration.

Reads the database URL from app Settings (not alembic.ini) so there
is one source of truth for credentials. Imports Base.metadata so
autogenerate can detect model changes.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

import backend.app.models  # noqa: F401
from alembic import context
from backend.app.core.config import get_settings
from backend.app.core.database import Base

# Alembic Config object — provides access to values in alembic.ini
config = context.config

# Set the DB URL from app settings (sync driver for Alembic)
settings = get_settings()
sync_url = settings.database_url.replace("+asyncpg", "+psycopg2").replace("+aiosqlite", "")
config.set_main_option("sqlalchemy.url", sync_url)

# Python logging from the ini file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL (no Engine needed).
    Emits SQL to the script output instead of executing it.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates a sync Engine and runs migrations within a connection.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
