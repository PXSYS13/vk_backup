"""Весь бэкап по шагам: архив ВК → база → файлы по ссылкам → страницы архива.

1. Импорт: страницы архива ВК разбираются и складываются в базу (без сети).
2. Скачивание: фото, голосовые и документы по прямым ссылкам из архива — несколько
   потоков. Это единственный шаг, где программа ходит в интернет, и только на файловые
   серверы ВК (см. firewall.py). Шаг можно выключить: тогда сети нет вовсе.
3. Страницы: HTML-архив из базы, тоже без сети.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from vkbackup import firewall, importer, media
from vkbackup.archive import Archive, NotAnArchive
from vkbackup.files import keep_awake
from vkbackup.render import messages as render_messages
from vkbackup.render import sections as render_sections
from vkbackup.render.base import plural
from vkbackup.store import DB_NAME, Store

log = logging.getLogger("vkbackup")

SECTIONS = importer.SECTIONS
SECTION_TITLES = render_sections.TITLES


@dataclass
class Status:
    """Что сейчас происходит — для экрана программы."""
    state: str = "idle"          # idle / running / stopping / done / stopped / error
    step: str = ""               # import / download / render
    text: str = ""               # строка для человека
    done: int = 0
    total: int | None = None
    started_at: float | None = None
    finished_at: float | None = None
    problem: str | None = None   # archive / disk / error
    problem_text: str = ""
    counts: dict[str, int] = field(default_factory=dict)


class Backup:
    """Один бэкап в фоне. start() — запустить, stop() — остановить, snapshot() — что происходит."""

    def __init__(self) -> None:
        self.status = Status()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self.downloader: media.Downloader | None = None

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, archive_path: Path, root: Path, sections: list[str], download: bool) -> bool:
        with self._lock:
            if self.running():
                return False
            self._cancel = threading.Event()
            self.downloader = None
            self.status = Status(state="running", started_at=time.time(), text="Начинаю…")
            self._thread = threading.Thread(target=self._run, args=(archive_path, root, tuple(sections), download),
                                            name="backup", daemon=True)
            self._thread.start()
            return True

    def stop(self) -> None:
        if self.running():
            self.status.state = "stopping"
            self.status.text = "Останавливаю: дописываю текущее…"
            self._cancel.set()
            if self.downloader:
                self.downloader.abort()

    def wait(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def snapshot(self) -> dict:
        data = asdict(self.status)
        dl = self.downloader
        if dl is not None:
            data["downloaded_now"] = dl.done_count
            data["bytes_now"] = dl.bytes
        return data

    def _report(self, step: str, done: int, total: int | None, text: str) -> None:
        self.status.done, self.status.total, self.status.text = done, total, text

    def _run(self, archive_path: Path, root: Path, sections: tuple[str, ...], download: bool) -> None:
        st = self.status
        store = None
        try:
            if download and not firewall.installed():
                raise RuntimeError("сетевой замок должен стоять до любого запроса в сеть")
            root.mkdir(parents=True, exist_ok=True)
            store = Store(root / DB_NAME)
            with keep_awake(), Archive(archive_path) as archive:
                st.step = "import"
                ctx = importer.Ctx(archive=archive, store=store, sections=sections, download=download,
                                   cancel=self._cancel, report=lambda *a: self._report("import", *a[1:]))
                st.counts = importer.import_archive(ctx)
            if download:
                st.step = "download"
                self.downloader = media.Downloader(store, root)
                self.downloader.start()
                self.downloader.finish()
                while self.downloader.alive():
                    if self._cancel.is_set():
                        raise importer.Cancelled()
                    stats = store.media_stats()
                    left = sum(s.get("pending", 0) for s in stats.values())
                    total = sum(s.get("pending", 0) + s.get("done", 0) + s.get("failed", 0) for s in stats.values())
                    self._report("download", total - left, total, f"Скачиваю файлы по ссылкам из архива: осталось {left}")
                    time.sleep(0.5)
                if self.downloader.disk_error:
                    raise media.DiskProblem(self.downloader.disk_error)
            st.step = "render"
            self._report("render", 0, None, "Собираю страницы архива…")
            render_archive(store, root)
            st.state = "done"
            st.text = "Готово: архив собран"
        except importer.Cancelled:
            st.state = "stopped"
            st.text = "Остановлено. Нажмите «Продолжить» — уже скачанное второй раз не качается."
        except NotAnArchive as e:
            st.state, st.problem, st.problem_text = "error", "archive", str(e)
        except media.DiskProblem as e:
            st.state, st.problem, st.problem_text = "error", "disk", str(e)
        except Exception as e:  # noqa: BLE001 — показать человеку, а не уронить программу
            log.exception("бэкап упал")
            st.state, st.problem = "error", "error"
            st.problem_text = f"Непредвиденная ошибка: {type(e).__name__}: {e}"
        finally:
            if self.downloader:
                self.downloader.abort()
                self.downloader.join(10)
            st.finished_at = time.time()
            if store is not None:
                try:
                    if st.state != "done" and store.count("profile"):
                        render_archive(store, root)  # что успели — уже можно посмотреть
                except Exception:  # noqa: BLE001
                    log.exception("страницы архива не собрались")
                store.close()


def render_archive(store: Store, root: Path) -> dict[str, str]:
    """Все страницы архива из базы. Возвращает подписи разделов для главной."""
    render_sections.copy_style(root)
    sections: dict[str, str] = {}
    if store.count("conversation"):
        n = render_messages.render_all(store, root, render_sections.me_name(store))
        sections["messages"] = (f"{plural(n, 'беседа', 'беседы', 'бесед')}, "
                                f"{plural(store.message_count(), 'сообщение', 'сообщения', 'сообщений')}")
    if store.count("friend"):
        sections["friends"] = render_sections.render_friends(store, root)
    if store.count("photo"):
        sections["photos"] = render_sections.render_photos(store, root)
    if store.count("video"):
        sections["videos"] = render_sections.render_videos(store, root)
    if store.count("post"):
        sections["wall"] = render_sections.render_wall(store, root)
    if store.count("track"):
        sections["music"] = render_sections.render_music(store, root)
    if store.count("doc"):
        sections["docs"] = render_sections.render_docs(store, root)
    render_sections.render_index(store, root, sections)
    return sections
