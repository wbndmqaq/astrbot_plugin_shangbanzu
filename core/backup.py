"""数据备份：基于 sqlite3 在线 backup API 的安全快照。"""

import sqlite3
import time
from pathlib import Path

from .db import _write_lock


class BackupManager:
    def __init__(self, db_path: Path, backups_dir: Path, logger=None):
        self.db_path = Path(db_path)
        self.dir = Path(backups_dir)
        self.log = logger

    def _log(self, msg):
        if self.log:
            self.log.info(f"[上班族物语][备份] {msg}")

    def create(self, label: str = "") -> dict:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        safe_label = "".join(ch for ch in label if ch.isalnum() or ch in "-_")[:20]
        name = f"{stamp}_{safe_label}" if safe_label else stamp
        self.dir.mkdir(parents=True, exist_ok=True)
        dest_path = self.dir / f"{name}.db"
        src = sqlite3.connect(self.path(), timeout=15)
        dest = sqlite3.connect(dest_path, timeout=15)
        try:
            with _write_lock:
                src.backup(dest)
                dest.commit()
        finally:
            dest.close()
            src.close()
        size = dest_path.stat().st_size
        self._log(f"创建备份 {name} ({size // 1024} KB)")
        return {"name": name, "file": str(dest_path), "size": size}

    def path(self) -> Path:
        return self.db_path

    def list(self) -> list[dict]:
        if not self.dir.is_dir():
            return []
        out = []
        for p in sorted(self.dir.glob("*.db"), reverse=True):
            st = p.stat()
            out.append(
                {
                    "name": p.stem,
                    "size": st.st_size,
                    "mtime": int(st.st_mtime),
                    "time": time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)
                    ),
                }
            )
        return out

    def restore(self, name_or_index) -> dict | None:
        item = self._resolve(name_or_index)
        if item is None:
            return None
        target = self.dir / f"{item['name']}.db"
        # 用在线 backup API 恢复到运行中的主库，避免直接覆盖文件
        # 与 WAL 日志产生一致性风险
        src = sqlite3.connect(target, timeout=15)
        dst = sqlite3.connect(self.path(), timeout=15)
        try:
            with _write_lock:
                src.backup(dst)
                dst.commit()
        finally:
            dst.close()
            src.close()
        self._log(f"恢复备份 {item['name']}")
        return item

    def delete(self, name_or_index) -> dict | None:
        item = self._resolve(name_or_index)
        if item is None:
            return None
        (self.dir / f"{item['name']}.db").unlink(missing_ok=True)
        self._log(f"删除备份 {item['name']}")
        return item

    def _resolve(self, name_or_index) -> dict | None:
        items = self.list()
        if not items:
            return None
        s = str(name_or_index).strip()
        if s.isdigit():
            idx = int(s) - 1
            return items[idx] if 0 <= idx < len(items) else None
        for it in items:
            if s in it["name"]:
                return it
        return None
