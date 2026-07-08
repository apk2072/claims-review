import os
from logging.config import fileConfig

import sqlalchemy_aurora_data_api  # noqa: F401  (registers the postgresql+auroradataapi dialect)
from alembic import context
from common.models import Base
from sqlalchemy import create_engine, pool

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Build the Data-API SQLAlchemy URL.

    aurora_cluster_arn/secret_arn are NOT embedded in the URL — the
    aurora-data-api driver reads them from the AURORA_CLUSTER_ARN /
    AURORA_SECRET_ARN environment variables. This is deliberate: Aurora has
    no public endpoint (isolated subnet, by design), so migrations run over
    the RDS Data API instead of a direct psycopg connection. See
    common/README.md.
    """
    db_name = os.environ.get("AURORA_DATABASE_NAME", "claims_review")
    return f"postgresql+auroradataapi://:@/{db_name}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
