# app/db.py
import os
import time
import threading
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session, declarative_base

# ---- 配置 ----
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////tmp/litebook.db")
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))

print(f"[db] 使用数据库: {DATABASE_URL}")

# ---- 全局对象（会在 resume 时重建）----
_engine = None
SessionLocal = None
Base = declarative_base()

# 写闸门：set() 允许写；clear() 暂停写（新的 get_db 会等待）
_write_gate = threading.Event()
_write_gate.set()


def _build_engine():
    """创建 engine 与 SessionLocal。SQLite 设定 check_same_thread=False。"""
    connect_args = {"check_same_thread": False, "timeout": 30} if DATABASE_URL.startswith("sqlite") else {}
    engine = create_engine(
        DATABASE_URL,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        future=True,
    )

    # SQLite 连接参数：配合同步逻辑使用 DELETE，不要启 WAL
    if DATABASE_URL.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, connection_record):
            cur = dbapi_connection.cursor()
            # 与 sync.py 的 checkpoint 逻辑一致：主库无 WAL/SHM
            cur.execute("PRAGMA journal_mode=DELETE;")
            cur.execute("PRAGMA synchronous=NORMAL;")
            cur.execute("PRAGMA foreign_keys=ON;")
            cur.execute("PRAGMA busy_timeout=5000;")
            cur.close()

    session_cls = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return engine, session_cls


def _init_engine():
    global _engine, SessionLocal
    _engine, SessionLocal = _build_engine()


_init_engine()  # 模块导入时初始化


def recreate_engine():
    """重建连接池（resume 时调用）"""
    global _engine, SessionLocal
    try:
        if _engine is not None:
            _engine.dispose(close=True)
    finally:
        _engine, SessionLocal = _build_engine()


def stop_writers(timeout: float = 1.0):
    """
    暂停写入：
      1) 关闸：新的 get_db() 会在闸门等待
      2) 等待在途事务收尾（timeout 秒）
      3) 释放连接池（engine.dispose）
    """
    _write_gate.clear()
    time.sleep(timeout)
    if _engine is not None:
        _engine.dispose(close=True)


def resume_writers():
    """恢复写入：重建连接池 + 开闸"""
    recreate_engine()
    _write_gate.set()


@contextmanager
def get_db() -> Session:
    """
    FastAPI 依赖：写请求在闸门关闭期间会阻塞。
    如果你将此依赖用于“只读”路由且不希望被阻塞，可另外做一个只读依赖不等待闸门。
    """
    _write_gate.wait()  # 若 stop_writers() 已调用，这里会等待 resume_writers()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
