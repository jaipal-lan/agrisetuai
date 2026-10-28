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
    # Import models so they register on Base.metadata, then create tables.
    # Real deployments use migrations; metadata.create_all is fine for dev/SQLite.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
