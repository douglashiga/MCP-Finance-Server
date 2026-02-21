"""
Database configuration for the DataLoader.
Supports both SQLite (default) and PostgreSQL (production).
"""
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

# Database configuration
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL or not DATABASE_URL.startswith("postgresql"):
    raise RuntimeError(
        "DATABASE_URL environment variable must be set and start with 'postgresql'. "
        "SQLite is no longer supported. Please check your .env or docker-compose.yml."
    )

# Create engine for PostgreSQL
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    echo=False
)

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
