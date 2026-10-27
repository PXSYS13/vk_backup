"""Вложения на страницах архива: фото сеткой, голосовые — плеером, файлы — ссылкой на скачанное.

Если файл не скачался или ВК положил в архив только ссылку на свой сайт (видео, музыка,
стикеры, пересланные сообщения), вместо файла — подпись ВК и ссылка на страницу в ВК.
"""

from __future__ import annotations

from pathlib import Path

from vkbackup.media import exists
from vkbackup.render.base import ext_link, h, rel

ICONS = {"video": "▶", "audio": "♪", "file": "📄", "link": "↗", "sticker": "☺", "gift": "🎁",
         "call": "📞", "wall": "≡", "wall_reply": "≡", "fwd": "↪", "deleted": "✕", "poll": "?",
         "graffiti": "✎", "story": "◷", "market": "₽", "article": "≡", "playlist": "♪"}


def local(att: dict, root: Path) -> str | None:
    """Путь скачанного файла (от корня архива) или None, если файла на диске нет."""
    path = att.get("file")
    return path if path and exists(root, path) else None


def render(items: list | None, depth: int, root: Path, photo_lookup=None) -> str:
    """Все вложения одного сообщения или записи. photo_lookup(ссылка) — локальный файл фото
    по ссылке vk.com/photo… (на стене ВК даёт только такие ссылки, а сами фото — в альбомах)."""
    photos: list[str] = []
    parts: list[str] = []
    for att in items or []:
        if not isinstance(att, dict):
            continue
        if att.get("kind") in ("photo", "graffiti"):
            path = local(att, root) or (photo_lookup(att.get("link")) if photo_lookup else None)
            if path:
                src = h(rel(path, depth))
                photos.append(f'<a href="{src}" target="_blank"><img src="{src}" alt="" loading="lazy"></a>')
            else:
                parts.append(_label(att, "фото не скачалось" if att.get("url") else ""))
        else:
            parts.append(_one(att, depth, root))
    out = ""
    if photos:
        cls = "photos single" if len(photos) == 1 else "photos"
        out += f'<div class="{cls}">{"".join(photos)}</div>'
    out += "".join(parts)
    return f'<div class="att">{out}</div>' if out else ""


def _label(att: dict, note: str = "") -> str:
    kind = att.get("kind", "other")
    label = h(att.get("label") or kind)
    link = att.get("link")
    tail = f" · {ext_link(link, 'открыть в ВК')}" if link else ""
    note_html = f' <span class="missing">{h(note)}</span>' if note else ""
    return (f'<div class="file"><span class="ico">{ICONS.get(kind, "•")}</span>'
            f'<span>{label}{note_html}<span class="tiny">{tail}</span></span></div>')


def _one(att: dict, depth: int, root: Path) -> str:
    kind = att.get("kind")
    path = local(att, root)
    if kind == "voice":
        if path:
            return f'<div><audio controls preload="none" src="{h(rel(path, depth))}"></audio></div>'
        return _label({**att, "label": "Голосовое сообщение"}, "не скачалось" if att.get("url") else "")
    if kind == "file" and path:
        name = path.rsplit("/", 1)[-1]
        ext = name.rsplit(".", 1)[-1].upper()[:4] if "." in name else "FILE"
        src = h(rel(path, depth))
        if ext in ("JPG", "JPEG", "PNG", "GIF", "WEBP"):
            return f'<div class="photos single"><a href="{src}" target="_blank"><img src="{src}" alt="" loading="lazy"></a></div>'
        return (f'<div class="file"><span class="ico">{h(ext)}</span>'
                f'<a href="{src}" target="_blank">{h(name)}</a></div>')
    if kind == "file":
        return _label(att, "не скачался" if att.get("url") else "ВК дал только ссылку")
    if kind == "link":
        link = att.get("link") or ""
        return f'<div class="file"><span class="ico">↗</span><span>{ext_link(link, link)}</span></div>'
    if kind == "deleted":
        return '<div class="missing">сообщение удалено</div>'
    if kind == "fwd":
        n = int(att.get("count") or 1)
        return (f'<div class="fwd"><div class="fwd-head">↪ {h(att.get("label"))}</div>'
                f'<span class="tiny">ВК не кладёт пересланные сообщения в архив — только отметку о них</span></div>'
                if n else "")
    return _label(att)


def text_summary(items: list | None, root: Path) -> list[str]:
    """Вложения для TXT-версии: «[Фотография: messages/…/photos/1_1.jpg]», «[Видеозапись: ссылка]»."""
    out = []
    for att in items or []:
        if not isinstance(att, dict):
            continue
        detail = local(att, root) or att.get("link") or ""
        out.append(f"[{att.get('label') or att.get('kind')}{': ' + detail if detail else ''}]")
    return out
