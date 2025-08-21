import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

# 默认使用本地 SQLite 数据库文件，如需自定义可设置环境变量 DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./litebook.db")

# SQLite 在多线程环境下需要 check_same_thread=False
engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    } if DATABASE_URL.startswith("sqlite") else {},
    poolclass=QueuePool if DATABASE_URL.startswith("sqlite") else None,
    pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
    pool_pre_ping=True,
)


if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        # 更好的并发：允许多读单写
        cursor.execute("PRAGMA journal_mode=WAL;")
        # 保持较好的性能与可靠性
        cursor.execute("PRAGMA synchronous=NORMAL;")
        # 启用外键约束
        cursor.execute("PRAGMA foreign_keys=ON;")
        # 等待锁释放时间（毫秒）
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
