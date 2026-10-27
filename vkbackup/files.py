"""Имена файлов и папок: то, что пришло из ВК, должно стать допустимым именем на любой системе.

Имена альбомов, документов и бесед пишут люди: в них бывают «:», «?», «/» и имена вроде
«CON». Всё это превращается в безопасное имя, которое не уведёт файл за пределы архива.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import sys
from collections.abc import Iterator

IS_WINDOWS = sys.platform.startswith("win")

# Символы, запрещённые в именах на Windows. Слеши тоже: иначе имя стало бы путём
_FORBIDDEN = '<>:"|?*\\/'
# Зарезервированные имена Windows (и с любым расширением: «NUL.txt» — тоже устройство)
_RESERVED = {
    "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
    *(f"COM{i}" for i in "0123456789¹²³"),
    *(f"LPT{i}" for i in "0123456789¹²³"),
}
# Короче, чем позволяет система (255): к имени ещё допишутся номер и расширение
MAX_NAME = 120


def short_hash(text: str, n: int = 6) -> str:
    return hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()[:n]


def safe_name(name: str, limit: int = MAX_NAME) -> str:
    """Одно имя файла или папки без запрещённых знаков, не длиннее limit знаков."""
    out = "".join("_" if ch in _FORBIDDEN or ord(ch) < 32 else ch for ch in (name or ""))
    out = " ".join(out.split()).strip(" .")
    if not out:
        return "_"
    if out.split(".", 1)[0].strip().upper() in _RESERVED:
        out = "_" + out
    if len(out) > limit:
        stem, ext = os.path.splitext(out)
        if len(ext) > 10:
            stem, ext = out, ""
        out = stem[: limit - len(ext) - 7].rstrip(" .") + "_" + short_hash(name) + ext
    return out


def ext_from_url(url: str, default: str) -> str:
    """Расширение файла по адресу: «…/photo.jpg?size=…» → «.jpg»."""
    path = url.split("?", 1)[0].split("#", 1)[0]
    ext = os.path.splitext(path.rsplit("/", 1)[-1])[1].lower()
    if 1 < len(ext) <= 6 and ext[1:].isalnum():
        return ext
    return default


def inside(root: str, path: str) -> bool:
    """path лежит внутри root (после нормализации) — защита от «..» в собранных путях."""
    root = os.path.normcase(os.path.abspath(root))
    path = os.path.normcase(os.path.abspath(path))
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def long_path(path: str) -> str:
    r"""На Windows — префикс \\?\ для путей длиннее 240 знаков; на остальных — как есть."""
    if not IS_WINDOWS:
        return path
    p = os.path.abspath(path)
    if len(p) < 240 or p.startswith("\\\\?\\"):
        return p
    if p.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p[2:]
    return "\\\\?\\" + p


@contextlib.contextmanager
def keep_awake() -> Iterator[None]:
    """Не даёт Windows уснуть, пока идёт бэкап. Экран гаснуть может, система — нет.

    Флаг действует для вызывающего потока: звать из потока, который живёт весь бэкап.
    """
    if IS_WINDOWS:
        with contextlib.suppress(Exception):
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    try:
        yield
    finally:
        if IS_WINDOWS:
            with contextlib.suppress(Exception):
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
