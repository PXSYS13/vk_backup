"""/api/…: всё, что делает страница программы.

Сервер слушает только 127.0.0.1, а ports.csrf_guard не пускает запросы с чужих сайтов:
страница из интернета не может ни прочитать статус, ни нажать кнопку.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import webbrowser
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from vkbackup import APP_VERSION, firewall, media, stats, supporters
from vkbackup.archive import Archive, NotAnArchive
from vkbackup.backup import SECTION_TITLES, SECTIONS, Backup, render_archive
from vkbackup.files import is_program_page, long_path
from vkbackup.store import DB_NAME, Store
from webapp import config, dashboard, paths, ports

log = logging.getLogger("webui")
router = APIRouter()
backup = Backup()

# Папки самой программы: архив поверх них лечь не может
PROGRAM_SUBDIRS = ("vkbackup", "webapp", "webui_assets", "tests", "logs", ".git", ".venv", ".uv")
# Поиск отдаёт по столько сообщений за раз: «Показать ещё» просит следующую порцию
SEARCH_LIMIT = 500

# В папке архива лежат и страницы программы, и файлы, которые прислали люди. Чужой .html или .svg,
# открытый с адреса программы, работал бы от её имени: прочитал бы /api/search и увёл переписку.
# Поэтому как страница открывается только то, что собрала сама программа (files.is_program_page), а
# прямо в браузере показываются только типы, которые не исполняют скрипты. Всё остальное — скачать.
INLINE_TYPES = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif",
    ".ogg", ".oga", ".opus", ".mp3", ".m4a", ".aac", ".wav", ".flac",
    ".mp4", ".webm", ".mov", ".m4v",
    ".pdf", ".txt", ".csv", ".css",
})
# Если браузер всё же покажет такой файл, а не скачает: без скриптов, без адреса программы
DOWNLOAD_CSP = "sandbox; default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"


def _resp(ok: bool, msg: str, **extra) -> dict:
    return {"ok": ok, "msg": msg, **extra}


@router.get("/", response_class=HTMLResponse)
def index() -> str:
    html = (paths.TEMPLATES_DIR / "app.html").read_text(encoding="utf-8")
    return html.replace("__APP_VERSION__", APP_VERSION)


@router.get("/api/hello")
def hello() -> dict:
    return {"app": ports.APP_ID, "version": APP_VERSION, "folder": str(paths.PROJECT)}


def _archive_stats(folder: Path) -> dict | None:
    db = folder / DB_NAME
    if not db.exists():
        return None
    store = Store(db)
    try:
        runs = store.runs()
        return {
            **dashboard.counts(store),
            "media": store.media_stats(media.MAX_TRIES),
            "failed": store.failed_media(20),
            "index": (folder / "index.html").exists(),
            "stats_page": (folder / "stats" / "index.html").exists(),
            "name": (store.get("profile", "me") or {}).get("name") or "",
            "last_run": runs[0] if runs else None,
        }
    finally:
        store.close()


@router.get("/api/status")
def status() -> dict:
    settings = config.load()
    return {
        "version": APP_VERSION,
        "settings": settings,
        "sections": [{"key": k, "title": SECTION_TITLES[k]} for k in SECTIONS],
        "job": backup.snapshot(),
        "result": _archive_stats(Path(settings["folder"])),
        "network": firewall.snapshot(),
    }


@router.get("/api/find-archives")
def find_archives() -> dict:
    """ZIP-архивы ВК в «Загрузках»: внутри есть messages/index-messages.html или index.html с метками ВК."""
    found = []
    folder = paths.DOWNLOADS_DIR
    try:
        candidates = sorted(folder.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)[:40]
    except OSError:
        candidates = []
    for zip_path in candidates:
        try:
            with zipfile.ZipFile(zip_path) as z:
                if any(n.endswith("messages/index-messages.html") for n in z.namelist()):
                    st = zip_path.stat()
                    found.append({"path": str(zip_path), "size": st.st_size, "modified": st.st_mtime})
        except (OSError, zipfile.BadZipFile):
            continue
    return {"folder": str(folder), "archives": found}


class SettingsIn(BaseModel):
    archive: str
    folder: str
    sections: list[str]
    download: bool = True


def _clean(raw: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(raw.strip().strip('"'))))


def _check_archive(raw: str) -> tuple[Path, int | None]:
    path = _clean(raw)
    if not raw.strip():
        raise HTTPException(400, "Укажите, где лежит архив ВК: ZIP-файл или папка")
    try:
        with Archive(path) as a:
            return path, a.owner_id()
    except NotAnArchive as e:
        raise HTTPException(400, str(e)) from None
    except OSError as e:
        raise HTTPException(400, f"Не открыть архив: {e.strerror or e}") from None


def _check_folder(raw: str) -> Path:
    folder = _clean(raw)
    if not raw.strip() or not folder.is_absolute():
        raise HTTPException(400, "Укажите полный путь к папке, например D:\\Архив ВК")
    if folder.parent == folder:
        raise HTTPException(400, "Корень диска выбрать нельзя — укажите папку на нём")
    resolved = folder.resolve()
    program = paths.PROJECT.resolve()
    if resolved == program or any(resolved == program / d or (program / d) in resolved.parents
                                  for d in PROGRAM_SUBDIRS):
        raise HTTPException(400, "Эта папка — часть программы. Выберите другую.")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        raise HTTPException(400, f"В эту папку нельзя записать: {e.strerror or e}") from None
    return folder


@router.post("/api/settings")
def save_settings(body: SettingsIn) -> dict:
    if backup.running():
        raise HTTPException(409, "Сначала остановите бэкап")
    archive, owner = _check_archive(body.archive)
    folder = _check_folder(body.folder)
    sections = [s for s in body.sections if s in SECTIONS]
    if not sections:
        raise HTTPException(400, "Отметьте хотя бы один раздел")
    saved = config.save(str(archive), str(folder), sections, body.download)
    who = f" (архив страницы id{owner})" if owner else ""
    return _resp(True, f"Сохранено{who}", settings=saved)


@router.post("/api/start")
def start() -> dict:
    settings = config.load()
    archive, _owner = _check_archive(settings["archive"])
    folder = _check_folder(settings["folder"])
    if not backup.start(archive, folder, settings["sections"], settings["download"]):
        return _resp(False, "Бэкап уже идёт")
    log.info("бэкап запущен: разделы %s, скачивать файлы: %s", ",".join(settings["sections"]),
             settings["download"])
    return _resp(True, "Бэкап запущен")


@router.post("/api/stop")
def stop() -> dict:
    backup.stop()
    return _resp(True, "Останавливаю")


@router.post("/api/retry-now")
def retry_now() -> dict:
    if not backup.retry_now():
        return _resp(False, "Сейчас нечего повторять")
    return _resp(True, "Пробую сейчас")


def _store() -> tuple[Store, Path]:
    folder = Path(config.load()["folder"])
    if not (folder / DB_NAME).exists():
        raise HTTPException(400, "Архива ещё нет")
    return Store(folder / DB_NAME), folder


@router.post("/api/retry-failed")
def retry_failed() -> dict:
    if backup.running():
        raise HTTPException(409, "Дождитесь конца бэкапа")
    store, _folder = _store()
    try:
        n = store.retry_failed_media()
    finally:
        store.close()
    return _resp(True, f"Вернул в очередь: {n}. Нажмите «Сохранить» — программа попробует их снова.")


# Статистика считается за секунды и меняется только с новыми сообщениями: держим последнюю
_stats_cache: dict[tuple, dict] = {}


@router.get("/api/stats")
def get_stats() -> dict:
    store, folder = _store()
    try:
        key = (str(folder), store.message_count(), store.count("friend"), store.count("photo"))
        if key not in _stats_cache:
            _stats_cache.clear()
            _stats_cache[key] = stats.compute(store)
        return {**_stats_cache[key], "on_this_day": stats.on_this_day(store)}
    finally:
        store.close()


@router.get("/api/search")
def search(q: str = "", peer: int | None = None, limit: int = 100) -> dict:
    store, _folder = _store()
    try:
        return stats.search(store, q[:200], limit=max(1, min(limit, SEARCH_LIMIT)), peer_id=peer)
    finally:
        store.close()


@router.get("/api/chats")
def chats() -> dict:
    """Беседы для фильтра поиска."""
    store, _folder = _store()
    try:
        return {"chats": stats.chats(store)}
    finally:
        store.close()


@router.get("/api/supporters")
def get_supporters() -> dict:
    """«Нас поддерживают»: копия общего списка автора, пришедшая вместе с программой.

    За свежим списком программа никуда не ходит — он приходит с новой версией."""
    data = supporters.load_local(paths.SUPPORTERS_FILE) or {"updated": None, "supporters": []}
    top_min = data.get("top_min_rub", supporters.TOP_MIN_RUB)
    return {**data, "people": supporters.count_people(data["supporters"]),
            "top": supporters.top_supporters(data["supporters"], top_min), "top_min_rub": top_min}


@router.get("/api/dashboard")
def get_dashboard() -> dict:
    """Всё для экрана «Панель»: файлы по разделам, причины ошибок, диск, история запусков."""
    settings = config.load()
    archive = _clean(settings["archive"]) if settings["archive"].strip() else None
    return dashboard.build(archive, Path(settings["folder"]), settings["download"])


@router.get("/archive/{rel_path:path}")
def archive_file(rel_path: str = "index.html"):
    """Страницы и файлы готового архива — чтобы смотреть его прямо отсюда и открывать
    найденное сообщение. Только файлы внутри папки архива, только с этого компьютера."""
    folder = Path(config.load()["folder"]).resolve()
    target = (folder / (rel_path or "index.html")).resolve()
    if target.is_dir():
        target = target / "index.html"
    # База и её служебные файлы (-wal, -shm) — не страницы архива: в них все сообщения целиком
    if folder not in target.parents or target.name.startswith(DB_NAME) or not os.path.isfile(long_path(str(target))):
        raise HTTPException(404, "Такого файла в архиве нет")
    rel = target.relative_to(folder).as_posix()
    if is_program_page(rel) or target.suffix.lower() in INLINE_TYPES:
        return FileResponse(long_path(str(target)))
    # Тип оставляем настоящим: <img src="….svg"> на страницах архива по-прежнему показывает картинку
    return FileResponse(long_path(str(target)), filename=target.name,
                        headers={"Content-Security-Policy": DOWNLOAD_CSP})


@router.post("/api/render")
def render() -> dict:
    if backup.running():
        raise HTTPException(409, "Дождитесь конца бэкапа")
    store, folder = _store()
    try:
        render_archive(store, folder)
    finally:
        store.close()
    return _resp(True, "Страницы архива обновлены")


@router.post("/api/open-archive")
def open_archive() -> dict:
    index_file = Path(config.load()["folder"]) / "index.html"
    if not index_file.exists():
        raise HTTPException(400, "Архива ещё нет")
    _open_local(index_file)
    return _resp(True, "Открываю архив в браузере")


@router.post("/api/open-folder")
def open_folder() -> dict:
    folder = Path(config.load()["folder"])
    if not folder.exists():
        raise HTTPException(400, "Папки ещё нет")
    _open_local(folder)
    return _resp(True, "Открываю папку")


def _open_local(path: Path) -> None:
    """Открыть файл или папку на этом компьютере — браузером по умолчанию или проводником."""
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # noqa: S606 — только файлы архива, путь из настроек
    else:
        webbrowser.open(path.resolve().as_uri())


def code_fingerprints() -> list[dict]:
    """SHA-256 каждого файла с кодом программы: их можно сверить с файлами на GitHub."""
    out = []
    root = paths.PROJECT
    for folder in ("vkbackup", "webapp", "webui_assets"):
        for p in sorted((root / folder).rglob("*")):
            if p.is_file() and p.suffix in (".py", ".js", ".css", ".html") and "__pycache__" not in p.parts:
                out.append({"path": p.relative_to(root).as_posix(),
                            "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    for name in ("webui.py", "webui.bat", "webui.sh", "pyproject.toml", "uv.lock"):
        p = root / name
        if p.exists():
            out.append({"path": name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    return out


@router.get("/api/security")
def security() -> dict:
    """Всё для экрана «Безопасность»: белый список, с кем говорили, что не пустили, отпечатки кода."""
    return {"network": firewall.snapshot(), "code": code_fingerprints()}
