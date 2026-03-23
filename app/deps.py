# app/deps.py
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from urllib.parse import urlparse

from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

DATABASE_URL = os.getenv("DB_URL", "postgresql://localhost:5432/litebook")
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))

_parsed = urlparse(DATABASE_URL)
print(f"[deps] 使用数据库: {_parsed.scheme}://{_parsed.hostname}{_parsed.path}")

# 对外导出
engine: Optional[Engine] = None
SessionLocal: Optional[sessionmaker] = None


def _build_engine() -> tuple[Engine, sessionmaker]:
    eng = create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_pre_ping=True,
        future=True,
    )
    session_cls = sessionmaker(bind=eng, autoflush=False, autocommit=False, expire_on_commit=False)
    return eng, session_cls


def _init_engine() -> None:
    global engine, SessionLocal
    engine, SessionLocal = _build_engine()


_init_engine()


def recreate_engine() -> None:
    """如需在运行时重建连接池（极少需要），可调用此函数。"""
    global engine, SessionLocal
    try:
        if engine is not None:
            engine.dispose(close=True)
    finally:
        engine, SessionLocal = _build_engine()


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖。正常创建/关闭会话即可。"""
    assert SessionLocal is not None, "SessionLocal 未初始化"
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
