"""Database engine/session setup. SQLite, single-user/household scale."""

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def data_dir() -> Path:
    d = Path(os.environ.get("MEDIASHELF_DATA_DIR", "./data"))
    d.mkdir(parents=True, exist_ok=True)
    return d


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        db_path = data_dir() / "mediashelf.db"
        _engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_factory()() as session:
        yield session


def reset_engine_for_tests() -> None:
    """Drop the cached engine so tests can point MEDIASHELF_DATA_DIR elsewhere."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
