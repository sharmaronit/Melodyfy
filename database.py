"""
database.py — SQLAlchemy engine + session factory
Uses SQLite for development (no server needed).
Switch DATABASE_URL to postgresql://... for production.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./beatflow.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Call once at startup."""
    from models import User, Repository, Commit, Stem  # noqa: F401
    from models import Star, Follow, Comment            # noqa: F401 — registers new models
    Base.metadata.create_all(bind=engine)
