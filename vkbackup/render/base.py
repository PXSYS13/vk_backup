"""Общее для всех страниц архива: каркас страницы, экранирование, текст ВК, даты, файлы."""

from __future__ import annotations

import html
import os
import re
import time
from pathlib import Path

from vkbackup import APP_NAME, APP_VERSION

# Страница архива не может ничего загрузить из интернета и не выполняет скриптов.
# file: — чтобы Chrome и Edge показывали картинки соседних файлов при открытии с диска
CSP = ("default-src 'none'; img-src 'self' file: data:; media-src 'self' file:; "
       "style-src 'self' file:; script-src 'none'; connect-src 'none'; font-src 'none'; "
       "frame-src 'none'; object-src 'none'; form-action 'none'; base-uri 'none'")

MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря")


def h(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def page(title: str, body: str, depth: int, *, wide: bool = False) -> str:
    """Готовая страница. depth — сколько папок от корня архива (для пути к стилям)."""
    up = "../" * depth
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="referrer" content="no-referrer">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{h(title)}</title>
<link rel="stylesheet" href="{up}assets/style.css">
</head>
<body>
<div class="wrap{' wide' if wide else ''}">
{body}
<footer class="foot">Сохранено программой «{h(APP_NAME)}» {h(APP_VERSION)} · {h(time.strftime('%d.%m.%Y'))}
 · страница открыта с вашего диска и ничего не загружает из интернета</footer>
</div>
</body>
</html>
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def rel(path: str, depth: int) -> str:
    """Путь от корня архива → ссылка со страницы на глубине depth."""
    return "../" * depth + path.replace(os.sep, "/").replace("#", "%23").replace("?", "%3F")


def day(ts: int) -> str:
    t = time.localtime(ts)
    return f"{t.tm_mday} {MONTHS[t.tm_mon - 1]} {t.tm_year}"


def when(ts: int) -> str:
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(ts)) if ts else ""


def clock(ts: int) -> str:
    return time.strftime("%H:%M", time.localtime(ts)) if ts else ""


def duration(seconds: object) -> str:
    try:
        s = int(seconds or 0)
    except (TypeError, ValueError):
        return ""
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def size(n: object) -> str:
    try:
        b = float(n or 0)
    except (TypeError, ValueError):
        return ""
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if b < 1024 or unit == "ГБ":
            return f"{b:.0f} {unit}" if unit == "Б" else f"{b:.1f} {unit}"
        b /= 1024
    return ""


def vk_link(owner_id: int) -> str:
    return f"https://vk.com/id{owner_id}" if owner_id > 0 else f"https://vk.com/club{-owner_id}"


def ext_link(url: str, text: str) -> str:
    """Ссылка наружу: откроется только по клику и не передаст, откуда перешли."""
    return f'<a href="{h(url)}" target="_blank" rel="noreferrer noopener">{h(text)}</a>'


_MENTION = re.compile(r"\[((?:id|club|public|event)\d+)\|([^\]]{1,200})\]")
_URL = re.compile(r"(https?://[^\s<>\"']{3,2000})")


def vk_text(text: str) -> str:
    """Текст ВК → HTML: экранирование, упоминания [id1|Имя] — ссылками, адреса — ссылками,
    переводы строк — <br>."""
    if not text:
        return ""
    out = []
    pos = 0
    for m in _MENTION.finditer(text):
        out.append(_plain(text[pos:m.start()]))
        out.append(ext_link(f"https://vk.com/{m.group(1)}", m.group(2)))
        pos = m.end()
    out.append(_plain(text[pos:]))
    return "".join(out)


def _plain(text: str) -> str:
    parts = []
    pos = 0
    for m in _URL.finditer(text):
        parts.append(h(text[pos:m.start()]))
        url = m.group(1).rstrip(".,;:!?)»")
        parts.append(ext_link(url, url))
        parts.append(h(m.group(1)[len(url):]))
        pos = m.end()
    parts.append(h(text[pos:]))
    return "".join(parts).replace("\n", "<br>")


def initials(name: str) -> str:
    words = [w for w in re.split(r"\s+", name or "") if w and w[0].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "?"


def avatar(name: str, owner_id: int, photo: str | None = None, depth: int = 0) -> str:
    """Кружок с инициалами (или фото, если оно скачано). Цвет — по id, чтобы был постоянным."""
    if photo:
        return f'<img class="ava" src="{h(rel(photo, depth))}" alt="" loading="lazy">'
    return f'<span class="ava c{abs(owner_id) % 8}">{h(initials(name))}</span>'


def plural(n: int, one: str, few: str, many: str) -> str:
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        word = one
    elif 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        word = few
    else:
        word = many
    return f"{n:,}".replace(",", " ") + " " + word
