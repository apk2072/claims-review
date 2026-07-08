"""Engine/session factory. Components (pipeline, backend, agent) connect over
a real psycopg VPC connection; DATABASE_URL supplies whichever dialect the
caller needs (see common/README.md for the Data-API-based URL Alembic uses).
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def get_engine(database_url: str | None = None):
    url = database_url or os.environ["DATABASE_URL"]
    return create_engine(url)


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(database_url))
