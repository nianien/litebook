# app/sync.py
from __future__ import annotations
import os, shutil, sqlite3, signal, atexit, hashlib, asyncio, threading
from pathlib import Path
from fastapi import FastAPI
from contextlib import asynccontextmanager

# ========= 配置 =========
LOCAL_DB = Path(os.getenv("LOCAL_DB_PATH", f"./litebook.db"))  # 运行时本地 DB
GCS_DB = Path(os.getenv("GCS_DB_PATH", f"/mnt/gcs/litebook.db"))  # GCS FUSE 目标
SYNC_INTERVAL_SEC = int(os.getenv("SYNC_INTERVAL_SEC", "600"))  # 周期同步（秒）

CHECKSUM_FILE = LOCAL_DB.with_name(LOCAL_DB.name + ".sum")  # 本地 MD5 基准
SNAP_DB = LOCAL_DB.with_suffix(".snap")  # 本地快照（缩短暂停窗口）

# ========= 并发与状态 =========
shutdown_evt: asyncio.Event | None = None
_sync_mutex = threading.RLock()  # 串行化：周期 / 退出 / 信号
_finalized = False  # 是否已进行过“成功的最终同步”（受 _sync_mutex 保护）


# ========= 日志 =========
def log(msg: str): print(msg, flush=True)


# ========= 小工具 =========
def ensure_parent(p: Path): p.parent.mkdir(parents=True, exist_ok=True)


def md5_file(path: Path, chunk: int = 4 * 1024 * 1024) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(chunk), b""): h.update(buf)
    return h.hexdigest()


def copy_atomic(src: Path, dst: Path):
    """临时文件 + 原子替换；不保留元数据（适配 GCS FUSE）。"""
    ensure_parent(dst)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    shutil.copyfile(src, tmp)  # 避免 copystat/owner/mtime
    os.replace(tmp, dst)


def save_checksum(md5_hash: str):
    ensure_parent(CHECKSUM_FILE)
    tmp = CHECKSUM_FILE.with_suffix(CHECKSUM_FILE.suffix + ".tmp")
    tmp.write_text(md5_hash + "\n", encoding="utf-8")
    os.replace(tmp, CHECKSUM_FILE)


def load_checksum() -> str | None:
    try:
        return CHECKSUM_FILE.read_text(encoding="utf-8").strip() if CHECKSUM_FILE.exists() else None
    except Exception:
        return None


# ========= checkpoint =========
def checkpoint(db_path: Path, mode: str):
    """
    PRAGMA wal_checkpoint(PASSIVE|FULL|RESTART|TRUNCATE)
    返回 (busy, log, checkpointed) 或 None（部分环境不返回）
    """
    mode = mode.upper()
    log(f"🧩 [sync] checkpoint({mode}) 开始")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        cur = conn.cursor()
        cur.execute(f"PRAGMA wal_checkpoint({mode});")
        try:
            res = cur.fetchone()
        except Exception:
            res = None
        conn.commit()
        log(f"🧩 [sync] checkpoint({mode}) 完成，结果={res}")
        return res
    finally:
        conn.close()


# ========= 启动：对齐本地与 GCS =========
def start_from_gcs():
    log("🚚 启动：检测到 GCS 主库，复制到本地…")
    copy_atomic(GCS_DB, LOCAL_DB)
    base = md5_file(LOCAL_DB)
    save_checksum(base)
    log(f"✅ 启动：本地已对齐（md5={base}）")


# ========= 统一同步动作（含“最终化”幂等）=========
def sync_once(mode: str = "PASSIVE", *, reason: str = "periodic", finalize: bool = False) -> bool:
    """
    执行一次同步（带幂等最终化）：
      1) 若 finalize=True 且已最终化，则直接跳过
      2) checkpoint(mode)
      3) 快照 & MD5 比对
      4) 变化则上传 & 更新 .sum
      5) 若 finalize=True 且流程成功，则标记已最终化

    返回：success(bool) —— 流程是否成功（未上传但流程跑通也算 True）
    """
    mode = mode.upper()
    if mode not in {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}:
        raise ValueError(f"[sync] unsupported checkpoint mode: {mode}")

    global _finalized
    with _sync_mutex:
        # 幂等跳过（仅限最终化路径）
        if finalize and _finalized:
            log(f"🔒 已最终化，跳过（reason={reason}, mode={mode}）")
            return False

        if not LOCAL_DB.exists():
            log("❌ [sync] 本地 DB 不存在，跳过")
            return False

        log(f"🔁 [sync] 进入（mode={mode}, reason={reason}, finalize={finalize}）")

        # 1) checkpoint（尽力而为）
        try:
            checkpoint(LOCAL_DB, mode=mode)
        except Exception as e:
            log(f"⚠️ checkpoint({mode}) 异常：{e!r}")

        # 2) 快照
        shutil.copyfile(LOCAL_DB, SNAP_DB)
        log(f"📸 快照 {SNAP_DB}")

        # 3) MD5 比对
        base_md5 = load_checksum()
        snap_md5 = md5_file(SNAP_DB)
        log(f"🔎 基准={base_md5 if base_md5 else 'None'} / 快照={snap_md5}")

        success = True  # 默认成功；上传阶段抛错再置 False
        try:
            if base_md5 and snap_md5 == base_md5:
                log("✅ MD5 未变化，跳过上传")
            else:
                copy_atomic(SNAP_DB, GCS_DB)
                save_checksum(snap_md5)
                log(f"✅ 已同步到 GCS（mode={mode}，reason={reason}），md5={snap_md5}")
        except Exception as e:
            success = False
            log(f"❌ [sync] 上传失败：{e!r}")
        finally:
            try:
                SNAP_DB.unlink(missing_ok=True)
            except Exception:
                pass

        # 4) 最终化置位（仅在 finalize=True 且流程成功时）
        if finalize and success and not _finalized:
            _finalized = True
            log("🏁 已标记为最终同步完成")

        return success


# ========= Lifespan：安装周期任务 + 信号 + atexit =========
def setup_lifecycle(app: FastAPI, enable_periodic: bool = True):
    if not GCS_DB.exists():
        return
    """main.py 用：from .sync import setup_lifecycle; setup_lifecycle(app)"""
    _periodic_task: asyncio.Task | None = None

    async def periodic_sync():
        assert shutdown_evt is not None
        while not shutdown_evt.is_set():
            try:
                await asyncio.sleep(SYNC_INTERVAL_SEC)
                if shutdown_evt.is_set():
                    break
                log("[sync] 周期检查…")
                sync_once(mode="PASSIVE", reason="periodic", finalize=False)
                log("[sync] 周期检查完成")
            except asyncio.CancelledError:
                return
            except Exception as e:
                log(f"[sync] 周期任务异常：{repr(e)}")

    def _raw_signal_handler(signum, frame):
        log(f"📡 收到信号 {signum}，准备最终同步…")
        import threading as _t
        # 后台线程做最终同步（TRUNCATE，幂等）
        _t.Thread(
            target=lambda: sync_once(mode="TRUNCATE", reason=f"signal:{signum}", finalize=True),
            daemon=True,
        ).start()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        global shutdown_evt
        nonlocal _periodic_task

        shutdown_evt = asyncio.Event()

        # startup
        log("🚀 startup(lifespan): 初始化开始")
        start_from_gcs()

        # 安装信号（优先 loop.add_signal_handler）
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.add_signal_handler(sig, lambda s=sig: _raw_signal_handler(s, None))
                except NotImplementedError:
                    signal.signal(sig, _raw_signal_handler)
        except Exception:
            try:
                signal.signal(signal.SIGTERM, _raw_signal_handler)
                signal.signal(signal.SIGINT, _raw_signal_handler)
            except Exception:
                pass

        if enable_periodic and SYNC_INTERVAL_SEC > 0:
            _periodic_task = asyncio.create_task(periodic_sync())

        # 兜底：atexit（若信号/关停未跑到；幂等）
        atexit.register(lambda: sync_once(mode="TRUNCATE", reason="atexit", finalize=True))

        log("✅ lifecycle hooks installed (lifespan)")
        try:
            yield
        finally:
            # shutdown 阶段的“最后一搏”（幂等）
            if shutdown_evt:
                shutdown_evt.set()
            if _periodic_task:
                _periodic_task.cancel()
                try:
                    await _periodic_task
                except Exception:
                    pass
            sync_once(mode="TRUNCATE", reason="shutdown", finalize=True)

    app.router.lifespan_context = lifespan
