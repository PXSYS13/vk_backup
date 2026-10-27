"""Скачивание файлов из очереди: несколько потоков, пока идёт сбор, и до конца очереди после.

Файл скачивается во временный «имя.part» и переименовывается, только если пришёл целиком.
Уже лежащий на месте файл второй раз не качается. Если адрес устарел (ВК выдаёт адреса
файлов с подписью, и они живут не вечно), файл отмечается не скачанным: следующий запуск
бэкапа получит свежий адрес и докачает его.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

from vkbackup import firewall, net
from vkbackup.files import inside, long_path
from vkbackup.store import Store

log = logging.getLogger("vkbackup")

WORKERS = 4
MAX_TRIES = 3
# Ответы, после которых повторять бесполезно: файла нет или ссылка больше не действует
_GONE = {403, 404, 410}


class DiskProblem(Exception):
    """Не удалось записать файл на диск: нет места или нет доступа к папке."""


class Downloader:
    """Потоки скачивания над одной базой. stop() — дождаться конца очереди и выйти."""

    def __init__(self, store: Store, root: Path, workers: int = WORKERS):
        self.store = store
        self.root = root
        self.workers = workers
        self._threads: list[threading.Thread] = []
        self._finish = threading.Event()   # сбор закончен: докачать очередь и выйти
        self._abort = threading.Event()    # «Остановить»: выйти сразу
        self._claim = threading.Lock()
        self._busy: set[str] = set()
        self.done_count = 0
        self.failed_count = 0
        self.bytes = 0
        self.disk_error: str | None = None

    def start(self) -> None:
        for i in range(self.workers):
            t = threading.Thread(target=self._run, name=f"media-{i + 1}", daemon=True)
            t.start()
            self._threads.append(t)

    def finish(self) -> None:
        """Сбор закончен: потоки докачивают очередь и выходят."""
        self._finish.set()

    def abort(self) -> None:
        self._abort.set()
        self._finish.set()

    def join(self, timeout: float | None = None) -> None:
        for t in self._threads:
            t.join(timeout)

    def alive(self) -> bool:
        return any(t.is_alive() for t in self._threads)

    def _next(self) -> tuple[str, str] | None:
        with self._claim:
            for path, url in self.store.pending_media(limit=self.workers * 4 + 8, max_tries=MAX_TRIES):
                if path not in self._busy:
                    self._busy.add(path)
                    return path, url
        return None

    def _run(self) -> None:
        try:
            while not self._abort.is_set():
                job = self._next()
                if job is None:
                    if self._finish.is_set():
                        return
                    time.sleep(0.5)
                    continue
                try:
                    self._one(*job)
                finally:
                    with self._claim:
                        self._busy.discard(job[0])
        except DiskProblem as e:
            self.disk_error = str(e)
            self._abort.set()
        finally:
            net.close_all()

    def _one(self, rel_path: str, url: str) -> None:
        dest = self.root / rel_path
        if not inside(str(self.root), str(dest)):
            self.store.media_failed(rel_path, "путь вне папки архива", final=True)
            return
        target = Path(long_path(str(dest)))
        if target.exists() and target.stat().st_size > 0:
            self.store.media_done(rel_path, target.stat().st_size)
            self.done_count += 1
            return
        try:
            size = net.download(url, target)
        except firewall.BlockedConnection as e:
            self.store.media_failed(rel_path, f"замок: {e}", final=True)
            self.failed_count += 1
            return
        except net.NetError as e:
            final = e.status in _GONE
            self.store.media_failed(rel_path, str(e), final=final)
            if final:
                self.failed_count += 1
            return
        except OSError as e:
            raise DiskProblem(f"Не удалось записать {rel_path}: {e.strerror or e}") from None
        self.store.media_done(rel_path, size)
        self.done_count += 1
        self.bytes += size


def exists(root: Path, rel_path: str) -> bool:
    """Файл архива на месте — страницы показывают его, а не пометку «не скачано»."""
    return os.path.exists(long_path(str(root / rel_path)))
