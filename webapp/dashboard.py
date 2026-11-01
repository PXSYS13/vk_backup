"""«Панель»: всё об архиве на одном экране.

Что в архиве, сколько файлов скачано по разделам и почему остальные не скачались, сколько
места занято и свободно, как прошли последние запуски — и готов ли архив к тому, чтобы
удалить страницу ВК. Всё считается по базе и диску этого компьютера, без сети.
"""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

from vkbackup import firewall, media
from vkbackup.store import DB_NAME, RUNS_KEY, Store

__all__ = ["RUNS_KEY", "build", "classify", "counts", "failure_reasons"]

# Ссылки на файлы в архиве ВК подписаны и со временем перестают открываться. Точного срока ВК
# не называет; за неделю после выгрузки они ещё работали — дальше честнее предупредить
FRESH_DAYS = 7
# Фото и голосовые за годы переписки — это гигабайты: меньше гигабайта свободно — уже тесно
MIN_FREE = 1 << 30
DAY = 86400

REASONS = {
    "gone": ("ВК удалил файл или ссылка устарела",
             "Помогает свежий архив: закажите его, укажите в «Настройке» и нажмите «Сохранить ещё раз». "
             "Если ВК потерял файл после сбоя, его нет и на сайте ВК."),
    "server": ("Серверы ВК отвечали ошибкой",
               "Обычно это сбой на стороне ВК. Попробуйте ещё раз позже."),
    "network": ("Не было связи с серверами ВК",
                "Проверьте интернет и нажмите «Попробовать ещё раз»."),
    "lock": ("Адрес не из белого списка замка",
             "Программа не соединяется с чужими серверами — такой файл она не скачает."),
    "path": ("Странное имя файла в архиве",
             "Программа не пишет файлы за пределы папки архива."),
    "other": ("Другая ошибка", "Текст ошибки — в списке файлов на главной."),
}
_STATUS = re.compile(r"ответил (\d{3})")
_NETWORK = ("нет связи", "обрыв", "не целиком")


def classify(error: str | None) -> str:
    """Текст ошибки скачивания → понятная причина: gone, server, network, lock, path, other."""
    text = error or ""
    if m := _STATUS.search(text):
        return "gone" if int(m.group(1)) in media.GONE else "server"
    if any(word in text for word in _NETWORK):
        return "network"
    if text.startswith("замок"):
        return "lock"
    if "вне папки" in text or "занято страницей" in text:
        return "path"
    return "other"


def failure_reasons(store: Store) -> list[dict]:
    """Почему файлы не скачались — по причинам, самые частые первыми."""
    counted: dict[str, int] = {}
    for error, n in store.failed_errors():
        code = classify(error)
        counted[code] = counted.get(code, 0) + n
    return [{"code": code, "count": n, "title": REASONS[code][0], "hint": REASONS[code][1]}
            for code, n in sorted(counted.items(), key=lambda kv: (-kv[1], kv[0]))]


def counts(store: Store) -> dict[str, int]:
    """Сколько чего в архиве — для главной и для панели."""
    return {
        "messages": store.message_count(),
        "chats": store.count("conversation"),
        "friends": store.count("friend"),
        "photos": store.count("photo"),
        "videos": store.count("video"),
        "posts": store.count("post"),
        "tracks": store.count("track"),
        "docs": store.count("doc"),
    }


# ── Проверки «можно ли удалять страницу ВК» ──

def _check(key: str, ok: bool, title: str, hint: str) -> dict:
    return {"key": key, "ok": ok, "title": title, "hint": hint}


def pages_check(folder: Path, last_run: dict | None, imported: bool) -> dict:
    """Страницы есть и собраны из архива, разобранного целиком, а не на половине."""
    title = "Архив разобран, страницы собраны"
    if not (folder / "index.html").exists():
        return _check("pages", False, title,
                      "Нажмите «Сохранить» на главной: программа разберёт архив ВК и соберёт страницы.")
    state = (last_run or {}).get("state")
    if state in ("stopped", "running") or (state is None and not imported):
        return _check("pages", False, title,
                      "Последний бэкап не дошёл до конца: в страницах не всё. Нажмите «Продолжить» на главной.")
    if state == "error":
        return _check("pages", False, title,
                      "Последний бэкап закончился ошибкой. Исправьте её и нажмите «Сохранить ещё раз».")
    return _check("pages", True, title,
                  "Открываются двойным щелчком по index.html — без интернета и без программы.")


def files_check(stats: dict[str, dict[str, int]], download: bool, last_run: dict | None = None) -> dict:
    title = "Фото, голосовые и файлы скачаны"
    no_files = ("Файлы по ссылкам не скачивались: поставьте галочку «Скачать фото…» в «Настройке» "
                "и нажмите «Сохранить ещё раз».")
    if not download:
        return _check("files", False, title, no_files)
    if not stats:
        # Пустая очередь — ещё не «всё скачано»: файлы ставятся в очередь только бэкапом с галочкой
        run = last_run or {}
        if run.get("state") == "done" and run.get("download"):
            return _check("files", True, title, "В архиве нет файлов по ссылкам — скачивать нечего.")
        if not run or run.get("download") is False:
            return _check("files", False, title, no_files)
        return _check("files", False, title,
                      "Последний бэкап не дошёл до конца — нажмите «Продолжить» на главной.")
    left = {k: sum(s.get(k, 0) for s in stats.values()) for k in ("pending", "waiting", "failed")}
    if not any(left.values()):
        return _check("files", True, title, "Всё, что было по ссылкам в архиве, лежит в папке архива.")
    parts = []
    if left["pending"]:
        parts.append(f"в очереди {left['pending']}")
    if left["waiting"]:
        parts.append(f"ждут серверов ВК {left['waiting']} — программа докачает их сама, пока открыта")
    if left["failed"]:
        parts.append(f"не скачались {left['failed']} — причины ниже")
    return _check("files", False, title, "Файлы: " + "; ".join(parts) + ".")


def fresh_check(age_days: int | None, files_done: bool = False) -> dict:
    title = "Архив ВК свежий"
    if files_done:
        # Свежие ссылки нужны, только пока есть что качать
        return _check("fresh", True, title, "Все файлы уже скачаны — новый архив не нужен.")
    if age_days is None:
        return _check("fresh", False, title, "Архив ВК не найден по пути из «Настройки».")
    if age_days <= FRESH_DAYS:
        return _check("fresh", True, title, "Ссылки на фото в нём ещё действуют.")
    return _check("fresh", False, title,
                  f"Архиву {age_days} дн.: ссылки на файлы в нём могли устареть. Если что-то не скачалось, "
                  f"закажите свежий архив — уже скачанное второй раз не качается.")


def _existing(path: Path) -> Path:
    """Папки результата может ещё не быть — место считаем на диске, где она появится."""
    while not path.exists() and path.parent != path:
        path = path.parent
    return path


def _disk(folder: Path) -> tuple[int | None, int | None]:
    try:
        usage = shutil.disk_usage(_existing(folder))
    except OSError:
        return None, None
    return usage.free, usage.total


def disk_check(folder: Path) -> dict:
    free, _total = _disk(folder)
    title = "На диске хватает места"
    if free is None:
        return _check("disk", False, title, "Не получилось узнать, сколько места на диске.")
    gb = f"{free / (1 << 30):.1f}".replace(".", ",")
    if free >= MIN_FREE:
        return _check("disk", True, title, f"Свободно {gb} ГБ.")
    return _check("disk", False, title,
                  f"Свободно всего {gb} ГБ — освободите место: фото и голосовые могут занять гигабайты.")


def lock_check() -> dict:
    ok = firewall.installed()
    return _check("lock", ok, "Сетевой замок включён",
                  "Программа соединяется только с файловыми серверами ВК." if ok else
                  "Замок не стоит — перезапустите программу.")


# ── Сводка ──

def _archive(path: Path | None, now: float) -> dict:
    info = {"path": str(path or ""), "exists": False, "size": None, "modified": None, "age_days": None}
    if path is None:
        return info
    try:
        st = path.stat()
    except OSError:
        return info
    modified = st.st_mtime
    return {**info, "exists": True, "size": st.st_size if path.is_file() else None, "modified": modified,
            "age_days": max(0, int((now - modified) // DAY))}


def _network() -> dict:
    snap = firewall.snapshot()
    return {"installed": snap["installed"], "hosts": len(snap["hosts"]),
            "requests": sum(n for _host, n in snap["hosts"]), "blocked": len(snap["blocked"])}


def _db_bytes(folder: Path) -> int:
    """База вместе с -wal и -shm. Их удаляет SQLite, когда закрывается соединение, — в любой момент."""
    total = 0
    for p in folder.glob(DB_NAME + "*"):
        try:
            total += p.stat().st_size
        except OSError:
            continue
    return total


def build(archive: Path | None, folder: Path, download: bool, now: float | None = None) -> dict:
    """Всё для экрана «Панель»."""
    now = time.time() if now is None else now
    db = folder / DB_NAME
    ready = db.exists()
    content, stats, reasons, runs, imported_at = None, {}, [], [], None
    if ready:
        store = Store(db)
        try:
            content = counts(store)
            stats = store.media_stats(media.MAX_TRIES)
            reasons = failure_reasons(store)
            runs = store.runs()
            imported_at = store.get_progress("imported_at")
        finally:
            store.close()
    archive_info = _archive(archive, now)
    free, total = _disk(folder)
    last_run = runs[0] if runs else None
    files = files_check(stats, download, last_run)
    db_bytes = _db_bytes(folder) if ready else 0
    return {
        "ready": ready,
        "content": content,
        "media": stats,
        "reasons": reasons,
        "runs": runs,
        "imported_at": imported_at,
        "archive": archive_info,
        "folder": {"path": str(folder), "exists": folder.exists(), "index": (folder / "index.html").exists(),
                   "db_bytes": db_bytes, "files_bytes": sum(s["bytes"] for s in stats.values()),
                   "disk_free": free, "disk_total": total},
        "network": _network(),
        "download": download,
        "checks": [pages_check(folder, last_run, imported_at is not None), files,
                   fresh_check(archive_info["age_days"], files["ok"]), disk_check(folder), lock_check()],
    }
