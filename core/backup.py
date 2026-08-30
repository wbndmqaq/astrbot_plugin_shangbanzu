"""数据备份：基于 sqlite3 在线 backup API 的安全快照。"""

import sqlite3
import time
from pathlib import Path

from .db import COLUMNS, _write_lock

# 保留的最大快照数量：超出后自动淘汰最旧的，避免备份目录无限增长
MAX_KEEP = 20


class BackupManager:
    def __init__(self, db_path: Path, backups_dir: Path, logger=None, max_keep: int = MAX_KEEP):
        self.db_path = Path(db_path)
        self.dir = Path(backups_dir)
        self.log = logger
        self.max_keep = max(1, int(max_keep))

    def _log(self, msg):
        if self.log:
            self.log.info(f"[上班族物语][备份] {msg}")

    def create(self, label: str = "") -> dict:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        safe_label = "".join(ch for ch in label if ch.isalnum() or ch in "-_")[:20]
        name = f"{stamp}_{safe_label}" if safe_label else stamp
        self.dir.mkdir(parents=True, exist_ok=True)
        # 同一秒内重复创建不再互相覆盖
        base, seq = name, 1
        while (self.dir / f"{name}.db").exists():
            seq += 1
            name = f"{base}-{seq}"
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
        self.prune()
        return {"name": name, "file": str(dest_path), "size": size}

    def prune(self) -> int:
        """只保留最新的 max_keep 个快照，返回删除数量。"""
        items = self.list()
        removed = 0
        for it in items[self.max_keep :]:
            try:
                (self.dir / f"{it['name']}.db").unlink(missing_ok=True)
                removed += 1
            except OSError:
                continue
        if removed:
            self._log(f"淘汰旧备份 {removed} 个（上限 {self.max_keep}）")
        return removed

    def path(self) -> Path:
        return self.db_path

    def list(self) -> list[dict]:
        if not self.dir.is_dir():
            return []
        out = []
        for p in sorted(self.dir.glob("*.db"), key=lambda q: q.name, reverse=True):
            try:
                st = p.stat()
            except OSError:
                continue
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

    def verify(self, target: Path) -> str:
        """恢复前校验快照：完整性 + players 表列集必须覆盖当前 schema。

        返回 "" 表示可用，否则返回不可用原因（供上层直接回显）。
        """
        try:
            conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True, timeout=15)
        except sqlite3.Error as e:
            return f"无法打开备份文件：{e}"
        try:
            check = conn.execute("PRAGMA quick_check").fetchone()
            if not check or str(check[0]).lower() != "ok":
                return "备份文件完整性校验未通过，已拒绝恢复"
            cols = {r[1] for r in conn.execute("PRAGMA table_info(players)")}
            if not cols:
                return "备份中缺少 players 表，可能不是本插件的数据库"
            missing = [c for c in COLUMNS if c not in cols]
            if missing:
                return (
                    "备份来自更旧的插件版本，缺少字段："
                    + "、".join(missing[:6])
                    + ("…" if len(missing) > 6 else "")
                    + "，已拒绝恢复以避免存档损坏"
                )
        except sqlite3.Error as e:
            return f"备份校验失败：{e}"
        finally:
            conn.close()
        return ""

    def restore(self, name_or_index) -> dict | None:
        """恢复快照到运行中的主库。

        返回 None 表示没找到；返回 dict 且带 "error" 键表示校验未通过。
        """
        item = self._resolve(name_or_index)
        if item is None:
            return None
        target = self.dir / f"{item['name']}.db"
        reason = self.verify(target)
        if reason:
            self._log(f"拒绝恢复 {item['name']}：{reason}")
            return {**item, "error": reason}
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
        """解析备份标识：纯数字按 1 起序号，否则要求名称精确匹配。

        故意不做模糊/子串匹配——恢复与删除都是破坏性操作，
        「差不多像」的输入必须失败而不是命中一个碰巧排在前面的快照。
        """
        items = self.list()
        s = str(name_or_index or "").strip()
        if not items or not s:
            return None
        if s.isdigit() and len(s) <= 6:
            idx = int(s) - 1
            return items[idx] if 0 <= idx < len(items) else None
        for it in items:
            if s == it["name"]:
                return it
        return None
