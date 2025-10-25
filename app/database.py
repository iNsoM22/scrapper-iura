from __future__ import annotations
import os
from supabase import create_client, Client
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Keep DATABASE_URL for Alembic migrations only
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./scapper.db")


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models (used by Alembic for migrations only)"""
    pass


def get_engine(echo: bool = None):
    """Get SQLAlchemy engine (for Alembic migrations only)"""
    if echo is None:
        echo = os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true"
    return create_engine(DATABASE_URL, echo=echo)


# Initialize Supabase client
_supabase_client: Client = None


def get_supabase() -> Client:
    """Get or create Supabase client instance"""
    global _supabase_client
    if _supabase_client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client
