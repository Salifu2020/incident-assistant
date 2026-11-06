"""
Database connection and session management for PostgreSQL.
"""
import os
from sqlalchemy import create_engine, Column, String, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()

# User model
class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user", nullable=False)
    first_name = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    password_changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)
    active = Column(Boolean, default=True, nullable=False)

# Database engine and session
_engine = None
_SessionLocal = None

def get_database_url() -> str:
    """Get database URL from environment variable."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        # Fallback to local PostgreSQL for development
        database_url = os.environ.get(
            "POSTGRES_URL",
            "postgresql://postgres:postgres@localhost:5432/incident_assistant"
        )
    
    # Render provides DATABASE_URL in format: postgresql://user:pass@host:port/dbname
    # SQLAlchemy needs: postgresql+psycopg2://user:pass@host:port/dbname
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    
    return database_url

def _use_local_storage() -> bool:
    """Local JSON auth + on-disk Chroma. Skips a remote Postgres that may be down."""
    flag = os.environ.get("USE_LOCAL_STORAGE", "").strip().lower()
    return flag in ("1", "true", "yes", "on")


def init_db():
    """Initialize database connection and create tables."""
    global _engine, _SessionLocal

    if _use_local_storage():
        logger.info("Using local JSON auth store at data/ (remote database skipped)")
        _engine = None
        _SessionLocal = None
        return

    try:
        database_url = get_database_url()
        logger.info(f"Connecting to database: {database_url.split('@')[1] if '@' in database_url else 'local'}")
        
        _engine = create_engine(
            database_url,
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=300,    # Recycle connections after 5 minutes
        )
        
        # Create all tables
        Base.metadata.create_all(bind=_engine)
        
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        logger.info("✅ Database initialized successfully")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        # Fall back to JSON file storage if database fails
        logger.warning("⚠️ Falling back to JSON file storage")
        _engine = None
        _SessionLocal = None

def get_db() -> Session:
    """Get database session."""
    if _SessionLocal is None:
        init_db()
    
    if _SessionLocal is None:
        return None  # Database not available, will use JSON fallback
    
    db = _SessionLocal()
    try:
        return db
    except Exception as e:
        logger.error(f"Database session error: {e}")
        db.close()
        raise

def is_db_available() -> bool:
    """Check if database is available."""
    return _engine is not None and _SessionLocal is not None



