from __future__ import annotations
from contextlib import contextmanager
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./scapper.db")


class Base(DeclarativeBase):
    pass


def get_engine(echo: bool = None):
    if echo is None:
        echo = os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true"
    return create_engine(DATABASE_URL, echo=echo)


SessionLocal = sessionmaker(bind=get_engine(), autoflush=False)


@contextmanager
def get_session():
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
