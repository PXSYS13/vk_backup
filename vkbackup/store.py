"""База SQLite: что уже собрано из ВК и какие файлы уже скачаны.

Лежит в папке архива (vk_backup.db) — вместе с самим архивом, никуда не отправляется.
По ней бэкап продолжается с того же места после перезапуска, и из неё же строятся
HTML-страницы: ответы ВК хранятся как есть (JSON), без пересказа.

Таблицы:
  objects   ответы ВК по разделам: kind (friend, photo, post, …) + key → JSON
  messages  сообщения переписок: peer_id + id → JSON (отдельно — их бывают сотни тысяч)
  progress  докуда дошёл каждый раздел (курсор), чтобы не начинать сначала
  media     файлы к скачиванию: куда положить, откуда взять, скачан ли
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

DB_NAME = "vk_backup.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS objects (
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (kind, key)
);
CREATE TABLE IF NOT EXISTS messages (
    peer_id INTEGER NOT NULL,
    id INTEGER NOT NULL,
    date INTEGER NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (peer_id, id)
);
CREATE TABLE IF NOT EXISTS progress (
    section TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS media (
    path TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    section TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    size INTEGER,
    error TEXT,
    tries INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_media_status ON media(status, section);
"""


class Store:
    """Одна база на один архив. Соединение — своё у каждого потока."""

    def __init__(self, path: Path):
        self.path = path
        self._tls = threading.local()
        self._all: list[sqlite3.Connection] = []
        self._lock = threading.Lock()
        with self.tx() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._tls, "conn", None)
        if conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._tls.conn = conn
            with self._lock:
                self._all.append(conn)
        return conn

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._conn()
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise

    def close(self) -> None:
        with self._lock:
            for conn in self._all:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            self._all.clear()
        self._tls = threading.local()

    # ── Объекты ВК ──

    def put(self, kind: str, key: object, data: object) -> None:
        self.put_many(kind, [(key, data)])

    def put_many(self, kind: str, items: Iterable[tuple[object, object]]) -> int:
        rows = [(kind, str(k), json.dumps(v, ensure_ascii=False)) for k, v in items]
        if rows:
            with self.tx() as c:
                c.executemany("INSERT OR REPLACE INTO objects(kind, key, data) VALUES (?, ?, ?)", rows)
        return len(rows)

    def get(self, kind: str, key: object) -> object | None:
        row = self._conn().execute("SELECT data FROM objects WHERE kind=? AND key=?",
                                   (kind, str(key))).fetchone()
        return json.loads(row[0]) if row else None

    def all(self, kind: str) -> list:
        rows = self._conn().execute("SELECT data FROM objects WHERE kind=? ORDER BY rowid",
                                    (kind,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def count(self, kind: str) -> int:
        return self._conn().execute("SELECT COUNT(*) FROM objects WHERE kind=?", (kind,)).fetchone()[0]

    # ── Сообщения ──

    def put_messages(self, peer_id: int, items: Iterable[dict]) -> int:
        rows = [(peer_id, int(m["id"]), int(m.get("date") or 0), json.dumps(m, ensure_ascii=False))
                for m in items if m.get("id")]
        if rows:
            with self.tx() as c:
                c.executemany("INSERT OR REPLACE INTO messages(peer_id, id, date, data) VALUES (?, ?, ?, ?)",
                              rows)
        return len(rows)

    def messages(self, peer_id: int) -> Iterator[dict]:
        """Сообщения переписки по порядку — от первого к последнему."""
        cur = self._conn().execute("SELECT data FROM messages WHERE peer_id=? ORDER BY id", (peer_id,))
        for (data,) in cur:
            yield json.loads(data)

    def message_count(self, peer_id: int | None = None) -> int:
        if peer_id is None:
            return self._conn().execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        return self._conn().execute("SELECT COUNT(*) FROM messages WHERE peer_id=?",
                                    (peer_id,)).fetchone()[0]

    def last_message_id(self, peer_id: int) -> int:
        row = self._conn().execute("SELECT MAX(id) FROM messages WHERE peer_id=?", (peer_id,)).fetchone()
        return int(row[0] or 0)

    # ── Курсоры разделов ──

    def get_progress(self, section: str, default: object = None) -> object:
        row = self._conn().execute("SELECT value FROM progress WHERE section=?", (section,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_progress(self, section: str, value: object) -> None:
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO progress(section, value) VALUES (?, ?)",
                      (section, json.dumps(value, ensure_ascii=False)))

    # ── Файлы ──

    def add_media(self, path: str, url: str, section: str) -> bool:
        """Файл в очередь. Уже скачанный не трогаем; у ждущего обновляем адрес — ВК выдаёт
        адреса файлов с подписью, и свежий адрес надёжнее старого."""
        with self.tx() as c:
            cur = c.execute(
                "INSERT INTO media(path, url, section) VALUES (?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET url=excluded.url "
                "WHERE media.status != 'done'",
                (path, url, section))
            return cur.rowcount > 0

    def pending_media(self, limit: int = 200, max_tries: int = 3) -> list[tuple[str, str]]:
        rows = self._conn().execute(
            "SELECT path, url FROM media WHERE status='pending' AND tries < ? ORDER BY rowid LIMIT ?",
            (max_tries, limit)).fetchall()
        return [(r[0], r[1]) for r in rows]

    def media_done(self, path: str, size: int) -> None:
        with self.tx() as c:
            c.execute("UPDATE media SET status='done', size=?, error=NULL WHERE path=?", (size, path))

    def media_failed(self, path: str, error: str, final: bool) -> None:
        with self.tx() as c:
            c.execute("UPDATE media SET tries=tries+1, error=?, status=? WHERE path=?",
                      (error[:300], "failed" if final else "pending", path))

    def media_status(self, path: str) -> str | None:
        row = self._conn().execute("SELECT status FROM media WHERE path=?", (path,)).fetchone()
        return row[0] if row else None

    def media_stats(self) -> dict[str, dict[str, int]]:
        """{раздел: {pending, done, failed, bytes}}."""
        out: dict[str, dict[str, int]] = {}
        for section, status, n, size in self._conn().execute(
                "SELECT section, status, COUNT(*), COALESCE(SUM(size), 0) FROM media GROUP BY section, status"):
            s = out.setdefault(section, {"pending": 0, "done": 0, "failed": 0, "bytes": 0})
            s[status] = n
            s["bytes"] += size
        return out

    def failed_media(self, limit: int = 50) -> list[dict]:
        rows = self._conn().execute(
            "SELECT path, section, error FROM media WHERE status='failed' ORDER BY rowid LIMIT ?",
            (limit,)).fetchall()
        return [{"path": p, "section": s, "error": e} for p, s, e in rows]

    def retry_failed_media(self) -> int:
        with self.tx() as c:
            return c.execute("UPDATE media SET status='pending', tries=0 WHERE status='failed'").rowcount
