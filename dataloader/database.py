"""
Database configuration for the DataLoader.
Supports both SQLite (default) and PostgreSQL (production).
"""
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

# Database configuration
# Set DATABASE_URL environment variable to use PostgreSQL:
# export DATABASE_URL="postgresql://user:password@localhost:5432/finance_db"
# Otherwise defaults to SQLite
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(os.path.dirname(__file__), 'finance_data.db')}"
)

# Create engine with appropriate settings
if DATABASE_URL.startswith("postgresql"):
    # PostgreSQL settings
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # Verify connections before using
        echo=False
    )
else:
    # SQLite settings
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False
    )

# Enable WAL mode and foreign keys for SQLite only
if not DATABASE_URL.startswith("postgresql"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session() -> Generator[Session, None, None]:
    """Yield a database session, auto-closing on exit."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db():
    """Create all tables."""
    from dataloader.models import Base
    Base.metadata.create_all(bind=engine)
