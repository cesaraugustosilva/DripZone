from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _sqlite_path_from_url(url: str) -> Path | None:
    if not url.startswith("sqlite:///"):
        return None
    value = url.removeprefix("sqlite:///")
    return Path(value)


def is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite")


def engine_options_for_url(url: str) -> dict:
    if is_sqlite_url(url):
        return {"connect_args": {"check_same_thread": False}, "future": True}
    return {"future": True}


db_path = _sqlite_path_from_url(settings.database_url)
if db_path is not None:
    db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(settings.database_url, **engine_options_for_url(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


if is_sqlite_url(settings.database_url):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
