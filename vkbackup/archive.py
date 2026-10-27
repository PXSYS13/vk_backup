"""Чтение архива данных ВК: ZIP-файл, как его отдал ВК, или уже распакованная папка.

Архив только читается: программа ничего в нём не меняет и не распаковывает на диск.
Страницы архива ВК бывают в кодировке windows-1251 (так их выдаёт ВК) и в UTF-8
(если архив кто-то пересохранил) — кодировка определяется по самим байтам.
"""

from __future__ import annotations

import base64
import json
import posixpath
import re
import zipfile
from pathlib import Path


class NotAnArchive(ValueError):
    """По этому пути нет архива данных ВК."""


# Файл, по которому архив ВК узнаётся: главная страница архива и список переписок
_MARKERS = ("index.html", "messages/index-messages.html")


class Archive:
    """Файлы архива по путям вида «messages/123/messages0.html» — из ZIP или из папки."""

    def __init__(self, path: Path):
        self.path = path
        self._zip: zipfile.ZipFile | None = None
        self._prefix = ""
        if path.is_file():
            try:
                self._zip = zipfile.ZipFile(path)
            except zipfile.BadZipFile:
                raise NotAnArchive("Это не ZIP-архив. Укажите файл, который прислал ВК, или папку, куда его распаковали.") from None
            names = [n for n in self._zip.namelist() if not n.endswith("/")]
            self._names = {}
            # Архив мог быть упакован с папкой верхнего уровня: «Archive/index.html»
            for marker in _MARKERS:
                hit = next((n for n in names if n == marker or n.endswith("/" + marker)), None)
                if hit:
                    self._prefix = hit[: -len(marker)]
                    break
            for n in names:
                if n.startswith(self._prefix):
                    self._names[n[len(self._prefix):]] = n
        elif path.is_dir():
            root = path
            if not any((root / m).exists() for m in _MARKERS):
                inner = [d for d in root.iterdir() if d.is_dir() and any((d / m).exists() for m in _MARKERS)]
                if len(inner) == 1:
                    root = inner[0]
            self._root = root
            self._names = {p.relative_to(root).as_posix(): p.relative_to(root).as_posix()
                           for p in root.rglob("*.html")}
        else:
            raise NotAnArchive("По этому пути ничего нет. Проверьте, где лежит архив.")
        if not any(m in self._names for m in _MARKERS):
            self.close()
            raise NotAnArchive("Это не архив данных ВКонтакте: в нём нет index.html и папки messages.")

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()
            self._zip = None

    def __enter__(self) -> Archive:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def names(self, pattern: str) -> list[str]:
        """Пути страниц, подходящие под регулярное выражение (целиком)."""
        rx = re.compile(pattern)
        return sorted(n for n in self._names if rx.fullmatch(n))

    def exists(self, name: str) -> bool:
        return name in self._names

    def read(self, name: str) -> str:
        """Текст страницы. Путь — только из names(): «..» и абсолютные пути не пройдут."""
        name = posixpath.normpath(name)
        if name not in self._names:
            raise FileNotFoundError(name)
        if self._zip is not None:
            data = self._zip.read(self._names[name])
        else:
            data = (self._root / self._names[name]).read_bytes()
        return decode(data)

    def owner_id(self) -> int | None:
        """Чей это архив: id из служебной метки jd на страницах ВК (base64 JSON с user_id)."""
        for name in ("index.html", "messages/index-messages.html"):
            if self.exists(name):
                m = re.search(r'<meta name="jd" content="([A-Za-z0-9+/=_-]+)"', self.read(name))
                if m:
                    try:
                        raw = m.group(1)
                        data = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
                        return int(data["user_id"])
                    except (ValueError, KeyError, TypeError):
                        pass
        return None


def decode(data: bytes) -> str:
    """UTF-8, если байты им являются, иначе windows-1251 (в ней ВК выдаёт архив)."""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1251", errors="replace")
