from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        # check_same_thread=False so the dev SQLite file works across FastAPI threads.
        return {"connect_args": {"check_same_thread": False}}
    # pool_pre_ping avoids stale connections on Postgres.
    return {"pool_pre_ping": True}


engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Fallback schema creation (dev/tests). Prefer run_migrations() — it is the
    # source of truth and matches production.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def run_migrations() -> None:
    """Run `alembic upgrade head` programmatically against settings.database_url."""
    import os

    from alembic import command
    from alembic.config import Config

    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    # Resolve script location absolutely so it works regardless of cwd.
    cfg.set_main_option("script_location", os.path.join(backend_dir, "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")
