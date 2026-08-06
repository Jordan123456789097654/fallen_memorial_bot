"""
Database engine, session management, and auto-migration helper.
Supports SQLite and PostgreSQL.
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings
from app.utils.logger import logger

db_url = settings.sqlalchemy_db_url
connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}

engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency yielding database session in FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initializes database tables and executes safe column migrations."""
    Base.metadata.create_all(bind=engine)
    run_migrations()


def run_migrations():
    """Executes safe ALTER TABLE statements to add missing columns to pre-existing tables."""
    cols_to_add = [
        ("admin_role_id", "VARCHAR(100)"),
        ("bot_nickname", "VARCHAR(100)"),
        ("enable_keep_alive", "BOOLEAN DEFAULT TRUE")
    ]

    for col_name, col_type in cols_to_add:
        try:
            with engine.begin() as conn:
                if "postgresql" in db_url or "postgres" in db_url:
                    conn.execute(text(f"ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS {col_name} {col_type};"))
                elif "sqlite" in db_url:
                    conn.execute(text(f"ALTER TABLE guild_configs ADD COLUMN {col_name} {col_type};"))
        except Exception as e:
            logger.debug(f"Migration note for {col_name}: {e}")

    logger.info("Database schema verification and column migrations completed.")
