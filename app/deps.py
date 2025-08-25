import os
import shutil
import signal
import atexit
import sqlite3
import json
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy.ext.declarative import declarative_base

# 路径配置
GCS_MOUNT = Path("/mnt/gcs")
LOCAL_DB = Path("./litebook.db")
CHECKSUM_FILE = Path("./db_checksum.json")

def get_file_checksum(file_path):
    """获取文件的校验信息"""
    if not file_path.exists():
        return None
    
    stat = file_path.stat()
    return {
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "ctime": stat.st_ctime
    }

def save_checksum(checksum_data):
    """保存校验信息到文件"""
    try:
        with open(CHECKSUM_FILE, 'w', encoding='utf-8') as f:
            json.dump(checksum_data, f, ensure_ascii=False, indent=2)
        print(f"✅ 校验信息已保存: {CHECKSUM_FILE}")
    except Exception as e:
        print(f"❌ 保存校验信息失败: {e}")

def load_checksum():
    """从文件加载校验信息"""
    try:
        if CHECKSUM_FILE.exists():
            with open(CHECKSUM_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"❌ 加载校验信息失败: {e}")
    return None

def copy_from_gcs():
    """从 GCS 复制数据库文件到本地（如果存在）"""
    if not GCS_MOUNT.exists():
        print("❌ GCS 挂载点不存在: /mnt/gcs")
        return
    
    if not GCS_MOUNT.is_dir():
        print("❌ GCS 挂载点不是目录: /mnt/gcs (可能是文件)")
        return
    
    gcs_db = GCS_MOUNT / "litebook.db"
    if not gcs_db.exists():
        print("❌ GCS 中未找到数据库文件: /mnt/gcs/litebook.db")
        return
    
    try:
        print("🔄 从 GCS 复制数据库到本地...")
        shutil.copy2(gcs_db, LOCAL_DB)
        
        # 复制完成后，生成校验文件
        checksum_data = get_file_checksum(LOCAL_DB)
        if checksum_data:
            save_checksum(checksum_data)
            print("✅ 复制成功，校验信息已保存")
        else:
            print("✅ 复制成功，但校验信息保存失败")
            
    except Exception as e:
        print(f"❌ 复制失败: {e}")

def sync_to_gcs():
    """将本地数据库同步到 GCS"""
    # 检查 GCS 挂载
    if not GCS_MOUNT.exists():
        print("❌ GCS 挂载点不存在: /mnt/gcs")
        return
    
    if not GCS_MOUNT.is_dir():
        print("❌ GCS 挂载点不是目录: /mnt/gcs")
        return
    
    # 检查本地数据库文件
    if not LOCAL_DB.exists():
        print("❌ 本地数据库文件不存在，无法同步")
        return
    
    # 先执行 checkpoint，确保 WAL 数据合并到主库
    print("🔄 执行 SQLite checkpoint...")
    try:
        with sqlite3.connect(LOCAL_DB) as conn:
            conn.execute("PRAGMA wal_checkpoint(FULL);")
        print("✅ checkpoint 完成")
    except Exception as e:
        print(f"❌ checkpoint 失败: {e}")
        return
    
    # 加载之前保存的校验信息
    saved_checksum = load_checksum()
    if not saved_checksum:
        print("❌ 未找到校验信息，无法判断文件变化")
        return
    
    # 获取 checkpoint 后的文件状态
    current_checksum = get_file_checksum(LOCAL_DB)
    if not current_checksum:
        print("❌ 无法获取当前文件校验信息")
        return
    
    # 检查 WAL 文件状态
    wal_file = LOCAL_DB.with_suffix('.db-wal')
    wal_size = wal_file.stat().st_size if wal_file.exists() else 0
    
    print(f"📊 文件状态检查:")
    print(f"  保存的校验: {saved_checksum['size']:,} 字节, 修改时间: {saved_checksum['mtime']}")
    print(f"  当前文件:  {current_checksum['size']:,} 字节, 修改时间: {current_checksum['mtime']}")
    print(f"  WAL文件大小: {wal_size:,} 字节")
    
    # 判断是否需要同步
    db_changed = (current_checksum["size"] != saved_checksum["size"] or 
                  current_checksum["mtime"] != saved_checksum["mtime"])
    
    if not db_changed and wal_size <= 1024:  # WAL 文件很小或不存在
        print("✅ 数据库文件无变化，WAL 已合并，无需同步")
        return
    
    if db_changed:
        print("🔄 检测到数据库文件变化，需要同步")
    elif wal_size > 1024:
        print("🔄 检测到 WAL 文件有数据，需要同步")
    
    gcs_db = GCS_MOUNT / "litebook.db"
    try:
        # 同步数据库到 GCS
        print("🔄 同步数据库到 GCS...")
        shutil.copy2(LOCAL_DB, gcs_db)
        
        # 同步完成后，更新校验信息
        print("🔄 更新校验信息...")
        new_checksum = get_file_checksum(LOCAL_DB)
        if new_checksum:
            save_checksum(new_checksum)
            print("✅ 同步成功，校验信息已更新")
        else:
            print("✅ 同步成功，但校验信息更新失败")
            
    except Exception as e:
        print(f"❌ 同步失败: {e}")

def signal_handler(signum, frame):
    """信号处理器，在容器关闭时同步数据"""
    print(f"\n📡 收到信号 {signum}，开始同步数据到 GCS...")
    sync_to_gcs()
    print("🔄 数据同步完成，准备关闭应用...")
    exit(0)

def register_shutdown_hooks():
    """注册关闭时的钩子函数"""
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    atexit.register(sync_to_gcs)
    print("✅ 已注册数据同步钩子函数")

# Startup actions
copy_from_gcs()
register_shutdown_hooks()

# 数据库连接配置 - 始终使用本地文件
DATABASE_URL = "sqlite:///./litebook.db"

print(f"使用数据库: {DATABASE_URL}")

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
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
