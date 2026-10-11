"""
Persistent store: user accounts and dataset sessions.

SQLite by default (zero-ops, the file lives in backend/data/cyberrisk.db).
Point DATABASE_URL at postgresql+psycopg2://... to move to Postgres without
code changes — the schema below is portable.

Also owns the per-request "which dataset am I looking at" resolution. Each
upload/demo run gets its own output directory, so the process-global caches
that used to leak one requester's data to every other client are gone: the
active session is resolved from the database per request, via a ContextVar.
"""

import logging
import os
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
    update,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{(DATA_DIR / 'cyberrisk.db').as_posix()}"

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String(64), unique=True, nullable=False, index=True),
    Column("password_hash", String(128), nullable=False),
    Column("salt", String(64), nullable=False),
    # Intentionally not a FK: datasets also references users, and SQLAlchemy
    # cannot topologically sort a cycle. SQLite does not enforce it anyway.
    Column("active_dataset_id", Integer, nullable=True),
    Column("created_at", DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)),
)

datasets = Table(
    "datasets",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, nullable=False, index=True),
    Column("session_id", String(128), unique=True, nullable=False),
    Column("data_dir", String(512), nullable=False),
    Column("output_dir", String(512), nullable=False),
    Column("asset_count", Integer, nullable=False, default=0),
    Column("created_at", DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)),
)

metadata.create_all(engine)


# ---------------------------------------------------------------------------
# Per-request session resolution
# ---------------------------------------------------------------------------

# (data_dir, output_dir) of the caller's active dataset, or None to fall
# back to the seed data + legacy root outputs/ (what `python -m
# risk_engine.pipeline` writes when run from the CLI).
_session_paths: ContextVar[Optional[Tuple[str, str]]] = ContextVar("session_paths", default=None)


def set_session_paths(data_dir: Optional[str], output_dir: Optional[str]) -> None:
    _session_paths.set((data_dir, output_dir) if data_dir and output_dir else None)


def current_paths() -> Tuple[Path, Path]:
    """(data_dir, output_dir) for the dataset this request is viewing."""
    paths = _session_paths.get()
    if paths:
        return Path(paths[0]), Path(paths[1])
    return DATA_DIR, OUTPUT_DIR


def has_session() -> bool:
    """True when this request resolved an active dataset for the caller."""
    return _session_paths.get() is not None


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def _row_to_dict(row) -> Optional[dict]:
    return dict(row._mapping) if row is not None else None


def create_user(username: str, password_hash: str, salt: str) -> int:
    with engine.begin() as conn:
        return conn.execute(
            insert(users).values(username=username, password_hash=password_hash, salt=salt)
        ).inserted_primary_key[0]


def get_user_by_username(username: str) -> Optional[dict]:
    with engine.connect() as conn:
        return _row_to_dict(
            conn.execute(select(users).where(users.c.username == username)).first()
        )


def get_user_by_id(user_id: int) -> Optional[dict]:
    with engine.connect() as conn:
        return _row_to_dict(
            conn.execute(select(users).where(users.c.id == user_id)).first()
        )


# ---------------------------------------------------------------------------
# Dataset sessions
# ---------------------------------------------------------------------------

def create_dataset(user_id: int, session_id: str, data_dir: str, output_dir: str, asset_count: int) -> int:
    with engine.begin() as conn:
        return conn.execute(
            insert(datasets).values(
                user_id=user_id,
                session_id=session_id,
                data_dir=data_dir,
                output_dir=output_dir,
                asset_count=asset_count,
            )
        ).inserted_primary_key[0]


def get_dataset_by_session_id(session_id: str) -> Optional[dict]:
    with engine.connect() as conn:
        return _row_to_dict(
            conn.execute(select(datasets).where(datasets.c.session_id == session_id)).first()
        )


def set_active_dataset(user_id: int, dataset_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(update(users).where(users.c.id == user_id).values(active_dataset_id=dataset_id))


def get_active_dataset(user_id: int) -> Optional[dict]:
    with engine.connect() as conn:
        row = conn.execute(
            select(users.c.active_dataset_id).where(users.c.id == user_id)
        ).first()
        if row is None or row[0] is None:
            return None
        return _row_to_dict(
            conn.execute(select(datasets).where(datasets.c.id == row[0])).first()
        )


def list_datasets(user_id: int, limit: int = 20) -> list:
    with engine.connect() as conn:
        rows = conn.execute(
            select(datasets)
            .where(datasets.c.user_id == user_id)
            .order_by(datasets.c.created_at.desc())
            .limit(limit)
        ).all()
        return [dict(r._mapping) for r in rows]
