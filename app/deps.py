# app/deps.py
from __future__ import annotations

import os
from typing import Generator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////tmp/litebook.db")
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))

print(f"[deps] 使用数据库: {DATABASE_URL}")

# 对外导出
engine: Optional[Engine] = None
SessionLocal: Optional[sessionmaker] = None
Base = declarative_base()


def _build_engine() -> tuple[Engine, sessionmaker]:
    is_sqlite = DATABASE_URL.startswith("sqlite")
    connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}

    # 关键点：
    # - SQLite 默认是 SingletonThreadPool，不利于多线程共享同一连接；这里显式使用 QueuePool。
    # - 非 SQLite 也保持 QueuePool（默认就是），参数通用。
    eng = create_engine(
        DATABASE_URL,
        connect_args=connect_args,
        poolclass=QueuePool,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_pre_ping=True,
        future=True,
    )

    if is_sqlite:
        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_connection, connection_record):
            # 每个物理连接建立时设置一次
            cur = dbapi_connection.cursor()
            # 运行期 WAL：写入更快，读写并发更友好
            cur.execute("PRAGMA journal_mode=WAL;")
            # 在 WAL 下，NORMAL 已经足够（性能/耐久性平衡）
            cur.execute("PRAGMA synchronous=NORMAL;")
            # 建议开启外键约束
            cur.execute("PRAGMA foreign_keys=ON;")
            # 忙等待时间（毫秒）——竞争写入时更友好
            cur.execute("PRAGMA busy_timeout=10000;")
            cur.close()

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
