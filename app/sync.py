# app/sync.py
from __future__ import annotations
import os, shutil, sqlite3, signal, atexit, hashlib, asyncio
from pathlib import Path
from fastapi import FastAPI

DB_NAME = os.getenv("LITEBOOK_DB_NAME", "litebook.db")
LOCAL_DB = Path(os.getenv("LOCAL_DB_PATH", f"/tmp/{DB_NAME}"))
GCS_DB = Path(os.getenv("GCS_DB_PATH", f"/mnt/gcs/{DB_NAME}"))
SYNC_INTERVAL_SEC = int(os.getenv("SYNC_INTERVAL_SEC", "600"))

# 本地 MD5 基准
CHECKSUM_FILE = LOCAL_DB.with_name(LOCAL_DB.name + ".sum")
# 本地快照（用于缩短暂停窗口）
SNAP_DB = LOCAL_DB.with_suffix(".snap")

shutdown_evt: asyncio.Event | None = None
sync_lock = asyncio.Lock()
_periodic_task: asyncio.Task | None = None
_stop_writers_cb = None
_resume_writers_cb = None


def ensure_parent(p: Path): p.parent.mkdir(parents=True, exist_ok=True)


def md5_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(chunk_size), b""):
            h.update(buf)
    return h.hexdigest()


def copy_atomic(src: Path, dst: Path):
    ensure_parent(dst)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    shutil.copyfile(src, tmp)  # 禁用 copy2/copystat/chown/chmod/utime
    os.replace(tmp, dst)


def checkpoint(db_path: Path):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("PRAGMA wal_checkpoint(FULL);")
    cur.execute("PRAGMA journal_mode=DELETE;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    conn.commit();
    conn.close()


def save_checksum_local(md5_hash: str):
    ensure_parent(CHECKSUM_FILE)
    tmp = CHECKSUM_FILE.with_suffix(CHECKSUM_FILE.suffix + ".tmp")
    tmp.write_text(md5_hash + "\n", encoding="utf-8")
    os.replace(tmp, CHECKSUM_FILE)


def load_checksum_local() -> str | None:
    try:
        return CHECKSUM_FILE.read_text(encoding="utf-8").strip() if CHECKSUM_FILE.exists() else None
    except Exception:
        return None


def start_from_gcs():
    if GCS_DB.exists():
        copy_atomic(GCS_DB, LOCAL_DB)
        save_checksum_local(md5_file(LOCAL_DB))
        print("✅ 启动：已从 GCS 拉取数据库，并写入本地 .sum")
    else:
        ensure_parent(LOCAL_DB)
        conn = sqlite3.connect(LOCAL_DB, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=DELETE;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.commit();
        conn.close()
        copy_atomic(LOCAL_DB, GCS_DB)
        save_checksum_local(md5_file(LOCAL_DB))
        print("✅ 启动：初始化空库并同步到 GCS，写入本地 .sum")


def sync_to_gcs_if_changed() -> bool:
    """
    暂停写 → checkpoint → 本地快照（SNAP_DB）→ 立即恢复写 → 用快照算 MD5/上传 → 更新 .sum → 清理快照
    """
    if not LOCAL_DB.exists():
        print("❌ 本地 DB 不存在，跳过同步")
        return False

    paused = False
    try:
        # 1) 暂停写入（可选，建议注入回调以缩短窗口）
        if callable(_stop_writers_cb):
            try:
                _stop_writers_cb()
                paused = True
            except Exception as e:
                print("stop_writers_cb failed:", repr(e))

        # 2) 合并 WAL，固定一致视图
        checkpoint(LOCAL_DB)

        # 3) 做本地快照（速度快，尽快结束暂停窗口）
        shutil.copyfile(LOCAL_DB, SNAP_DB)

    finally:
        # 4) 恢复写入（即使上面出错也尽量恢复）
        if paused and callable(_resume_writers_cb):
            try:
                _resume_writers_cb()
            except Exception as e:
                print("resume_writers_cb failed:", repr(e))

    # 5) 之后基于快照进行耗时操作（不再阻塞业务）
    try:
        saved_md5 = load_checksum_local()
        snap_md5 = md5_file(SNAP_DB)

        if saved_md5 and snap_md5 == saved_md5:
            print("✅ MD5 未变化（基于快照），跳过上传")
            return False

        copy_atomic(SNAP_DB, GCS_DB)
        save_checksum_local(snap_md5)
        print(f"✅ 已同步快照到 GCS，更新本地 md5={snap_md5[:8]}…")
        return True

    except Exception as e:
        print("❌ 同步失败：", repr(e))
        return False

    finally:
        try:
            SNAP_DB.unlink(missing_ok=True)
        except Exception:
            pass


async def sync_to_gcs_if_changed_async() -> bool:
    async with sync_lock:
        return sync_to_gcs_if_changed()


async def periodic_sync():
    assert shutdown_evt is not None
    while not shutdown_evt.is_set():
        try:
            await asyncio.sleep(SYNC_INTERVAL_SEC)
            if not LOCAL_DB.exists():
                continue
            print("[sync] 周期检查…")
            await sync_to_gcs_if_changed_async()
            print("[sync] 周期检查完成")
        except asyncio.CancelledError:
            return
        except Exception as e:
            print("[sync] 周期任务异常：", repr(e))


def register_lifecycle(app: FastAPI, stop_writers_cb=None, resume_writers_cb=None, enable_periodic=True):
    global _stop_writers_cb, _resume_writers_cb
    _stop_writers_cb = stop_writers_cb
    _resume_writers_cb = resume_writers_cb

    @app.on_event("startup")
    async def _startup():
        global shutdown_evt, _periodic_task
        shutdown_evt = asyncio.Event()
        start_from_gcs()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda: shutdown_evt.set())
            except NotImplementedError:
                pass

        if enable_periodic and SYNC_INTERVAL_SEC > 0:
            _periodic_task = asyncio.create_task(periodic_sync())

        atexit.register(lambda: asyncio.run(sync_to_gcs_if_changed_async()))
        print("✅ lifecycle hooks installed")

    @app.on_event("shutdown")
    async def _shutdown():
        if shutdown_evt:
            shutdown_evt.set()
        if _periodic_task:
            _periodic_task.cancel()
            try:
                await _periodic_task
            except Exception:
                pass
        try:
            await sync_to_gcs_if_changed_async()
            print("[sync] 最终同步完成")
        except Exception as e:
            print("[sync] 最终同步失败：", repr(e))

    @app.get("/_health/gcs")
    def _gcs_probe():
        def info(p: Path):
            return {"exists": p.exists(), "size": (p.stat().st_size if p.exists() else 0)}

        return {"ok": True, "local": info(LOCAL_DB), "gcs": info(GCS_DB)}
