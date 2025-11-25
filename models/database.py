"""
Database connection and session management.
Provides SQLAlchemy engine and session factory.
"""

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.pool import StaticPool
from typing import Generator
from contextlib import contextmanager

from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger()

# Create declarative base for ORM models
Base = declarative_base()

# Global engine and session factory
_engine = None
_SessionLocal = None


def get_engine():
    """Get or create the SQLAlchemy engine (singleton pattern)."""
    global _engine
    if _engine is None:
        settings = get_settings()
        logger.info(f"Creating database engine: {settings.database_url}")

        # SQLite-specific configuration
        if settings.database_url.startswith("sqlite"):
            _engine = create_engine(
                settings.database_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
                echo=False,  # Set to True for SQL query logging
            )

            # Enable foreign key constraints for SQLite
            @event.listens_for(_engine, "connect")
            def set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for better concurrency
                cursor.close()

        else:
            # PostgreSQL or other databases
            _engine = create_engine(
                settings.database_url,
                pool_pre_ping=True,
                echo=False,
            )

        logger.info("Database engine created successfully")

    return _engine


def get_session_factory():
    """Get or create the session factory (singleton pattern)."""
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
        )
        logger.info("Session factory created")

    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    Dependency function for FastAPI to get database session.

    Usage:
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database session.

    Usage:
        with get_db_session() as db:
            companies = db.query(Company).all()
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        db.close()


def create_all_tables():
    """Create all tables defined in ORM models."""
    from models.orm_models import (
        Company,
        Announcement,
        Analysis,
        StockData,
        EpisodicMemory,
        SemanticMemory,
        TimelineComparison,
        Evaluation,
        AgentTask,
    )

    engine = get_engine()
    logger.info("Creating all database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("All database tables created successfully")


def drop_all_tables():
    """Drop all tables (use with caution!)."""
    engine = get_engine()
    logger.warning("Dropping all database tables...")
    Base.metadata.drop_all(bind=engine)
    logger.warning("All database tables dropped")


def reset_database():
    """Drop and recreate all tables (use with caution!)."""
    logger.warning("Resetting database...")
    drop_all_tables()
    create_all_tables()
    logger.info("Database reset complete")


def check_database_connection() -> bool:
    """Check if database connection is working."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False
