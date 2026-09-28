import json
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings

# Configure SQLite for thread safety and WAL mode
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=False
)

# Enable WAL mode for SQLite
if settings.DATABASE_URL.startswith("sqlite"):
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        conn.exec_driver_sql("PRAGMA synchronous=NORMAL;")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all database tables and ensure migrations."""
    from app.db import models # noqa: F401
    Base.metadata.create_all(bind=engine)
    if settings.DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            try:
                conn.exec_driver_sql("ALTER TABLE human_actions ADD COLUMN checklist_json TEXT DEFAULT '{}';")
            except Exception:
                pass
            try:
                conn.exec_driver_sql("ALTER TABLE incidents ADD COLUMN train_no VARCHAR(32);")
            except Exception:
                pass
            try:
                conn.exec_driver_sql("ALTER TABLE incidents ADD COLUMN delay_min INTEGER DEFAULT 0;")
            except Exception:
                pass
