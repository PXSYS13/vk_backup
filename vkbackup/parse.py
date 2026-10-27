"""Разбор страниц архива ВК: из HTML — простые словари с текстом, датами и ссылками.

Разметку архива ВК генерирует сама: она однообразная, поэтому хватает регулярных
выражений по её классам (message__header, kludges, attachment__description, …). Всё, что
программа не узнала, не теряется: остаётся текстом с подписью ВК.

Даты в архиве — местное время без часового пояса («28 мая 2013 в 9:05:48»): так их и
храним, в секундах по часам этого компьютера.
"""

from __future__ import annotations

import html
import re
import time
import urllib.parse

from vkbackup import firewall

MONTHS = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6, "июл": 7,
    "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}
_DATE = re.compile(r"(\d{1,2})\s+([а-яё]{3})[а-яё]*\.?\s+(\d{4})"
                   r"(?:\s+в\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", re.I)
_TAG = re.compile(r"<[^>]+>")
_BR = re.compile(r"<br\s*/?>", re.I)


def parse_date(text: str) -> int | None:
    """«28 мая 2013 в 9:05:48», «7 мая 2026 в 21:15», «27 мая 2008» → секунды (местное время)."""
    m = _DATE.search(text or "")
    if not m:
        return None
    month = MONTHS.get(m.group(2).lower())
    if not month:
        return None
    hour, minute, sec = (int(m.group(i) or 0) for i in (4, 5, 6))
    try:
        return int(time.mktime((int(m.group(3)), month, int(m.group(1)), hour, minute, sec, 0, 0, -1)))
    except (OverflowError, ValueError):
        return None


def text_of(fragment: str) -> str:
    """HTML-кусок → обычный текст: <br> — перевод строки, теги — прочь, &amp; и &#128049; — знаками."""
    text = _BR.sub("\n", fragment or "")
    text = _TAG.sub("", text)
    text = html.unescape(text)
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "\n".join(lines).strip()


def content(page: str) -> str:
    """Содержимое страницы без шапки: всё после wrap_page_content."""
    i = page.find('class="wrap_page_content"')
    return page[i:] if i >= 0 else page


def items(page: str) -> list[str]:
    """Записи страницы: каждая начинается с <div class="item">."""
    parts = re.split(r'<div class="item">', content(page))
    return parts[1:]


def crumbs(page: str) -> list[str]:
    """«Хлебные крошки» шапки: ['Профиль', 'Сообщения', 'Имя собеседника']."""
    return [text_of(c) for c in re.findall(r'class="ui_crumb"[^>]*>(.*?)</(?:a|div)>', page, re.S)]


def owner_from_link(href: str) -> int | None:
    """vk.com/id123 → 123, vk.com/club45 / public45 / event45 → -45, иначе None."""
    m = re.search(r"vk\.(?:com|ru)/(id|club|public|event)(\d+)(?:[/?#]|$)", href or "")
    if not m:
        return None
    return int(m.group(2)) if m.group(1) == "id" else -int(m.group(2))


def is_file_url(url: str) -> bool:
    """Прямая ссылка на файл на сервере-хранилище ВК (её можно скачать без входа в аккаунт)."""
    try:
        parts = urllib.parse.urlsplit(url or "")
    except ValueError:
        return False
    return parts.scheme in ("https", "http") and firewall.host_allowed(parts.hostname or "")


# ── Вложения ──

_ATTACHMENT = re.compile(
    r'<div class="attachment">\s*<div class="attachment__description">(.*?)</div>\s*'
    r"(?:<a class=['\"]attachment__link['\"] href=['\"]([^'\"]*)['\"]>(.*?)</a>)?", re.S)

KINDS = {
    "фотография": "photo",
    "видеозапись": "video",
    "файл": "file",
    "документ": "file",
    "ссылка": "link",
    "стикер": "sticker",
    "аудиозапись": "audio",
    "подарок": "gift",
    "звонок": "call",
    "запись на стене": "wall",
    "комментарий на стене": "wall_reply",
    "сообщение удалено": "deleted",
    "граффити": "graffiti",
    "опрос": "poll",
    "история": "story",
    "товар": "market",
    "статья": "article",
    "плейлист": "playlist",
}


def attachments(kludges: str) -> list[dict]:
    """Вложения из блока kludges: тип, подпись ВК, прямая ссылка на файл (если есть) и ссылка на ВК."""
    out = []
    for m in _ATTACHMENT.finditer(kludges or ""):
        label = text_of(m.group(1))
        href = html.unescape(m.group(2) or "")
        link_text = text_of(m.group(3) or "")
        low = label.lower()
        kind = KINDS.get(low)
        if kind is None:
            kind = "fwd" if "прикреплённ" in low or "прикрепленн" in low else "other"
        att = {"kind": kind, "label": label}
        if is_file_url(href):
            att["url"] = href
            # У файлов текст ссылки — адрес на сайте ВК (vk.com/doc…): пригодится, если файл не скачается
            if re.match(r"(?:https?://)?vk\.(?:com|ru)/", link_text):
                att["link"] = link_text if link_text.startswith("http") else "https://" + link_text
        elif href:
            att["link"] = href
        if kind == "file" and "url" in att and re.search(r"/amsg\d*/", att["url"]):
            att["kind"] = "voice"
        if kind == "fwd":
            m2 = re.match(r"(\d+)", label)
            att["count"] = int(m2.group(1)) if m2 else 1
        out.append(att)
    return out


def _strip_attachments(kludges: str) -> str:
    return _ATTACHMENT.sub("", kludges or "")


# ── Переписки ──

_MSG_START = re.compile(r'<div class="message" data-id="(\d+)">')
_EDITED = re.compile(r"<span class=['\"]message-edited['\"][^>]*>.*?</span>", re.S)
_LINK = re.compile(r'<a [^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.S)


def messages_page(page: str) -> list[dict]:
    """Сообщения одной страницы переписки (ВК кладёт по 50 на страницу, новые — первыми)."""
    body = content(page)
    cut = body.find('<div class="pagination')
    if cut >= 0:
        body = body[:cut]
    starts = list(_MSG_START.finditer(body))
    out = []
    for i, m in enumerate(starts):
        chunk = body[m.end(): starts[i + 1].start() if i + 1 < len(starts) else len(body)]
        msg = _message(int(m.group(1)), chunk)
        if msg:
            out.append(msg)
    return out


def _message(mid: int, chunk: str) -> dict | None:
    hm = re.search(r'<div class="message__header">(.*?)</div>', chunk, re.S)
    if not hm:
        return None
    header = hm.group(1)
    edited = bool(_EDITED.search(header))
    header = _EDITED.sub("", header)
    link = _LINK.search(header)
    if link:
        name = text_of(link.group(2))
        from_id = owner_from_link(link.group(1))
        out = False
        when_text = header[link.end():]
    else:
        name, _, when_text = text_of(header).partition(",")
        name = name.strip()
        from_id = None
        out = name == "Вы"
    rest = chunk[hm.end():]
    bm = re.search(r"<div>", rest)
    body = rest[bm.end():] if bm else rest
    k = body.find('<div class="kludges">')
    if k >= 0:
        text_html, kludges = body[:k], body[k + len('<div class="kludges">'):]
    else:
        end = body.find("</div>")
        text_html, kludges = body[: end if end >= 0 else len(body)], ""
    msg = {
        "id": mid,
        "date": parse_date(when_text) or 0,
        "from_id": from_id,
        "from_name": name,
        "out": out,
        "text": text_of(text_html),
    }
    if edited:
        msg["edited"] = True
    atts = attachments(kludges)
    if atts:
        msg["attachments"] = atts
    service = text_of(_strip_attachments(kludges))
    if service:
        msg["service"] = service
    return msg


def chat_list(page: str) -> list[tuple[str, str]]:
    """Список переписок: [(папка собеседника, название)] в порядке архива."""
    return [(m.group(1), text_of(m.group(2)))
            for m in re.finditer(r'<a href="(-?\d+)/messages\d*\.html">(.*?)</a>', page, re.S)]


# ── Профиль и друзья ──

def page_info(page: str) -> dict:
    """«Информация о странице»: подпись → значение, плюс адрес аватарки."""
    info: list[tuple[str, str]] = []
    avatar = None
    for item in re.split(r'<div class="item">', content(page))[1:]:
        label = re.search(r'<div class="item__tertiary">(.*?)</div>', item, re.S)
        if not label:
            continue
        img = re.search(r'<img[^>]+src="([^"]+)"', item)
        if img and avatar is None:
            avatar = html.unescape(img.group(1))
            continue
        value = re.search(r"<div>(.*?)</div>", item[label.end():], re.S)
        if value:
            info.append((text_of(label.group(1)), text_of(value.group(1))))
    name = next((v for k, v in info if k.lower() == "полное имя"), "")
    return {"name": " ".join(name.split()), "info": info, "avatar_url": avatar if is_file_url(avatar or "") else None}


def friends_page(page: str) -> list[dict]:
    out = []
    for item in items(page):
        a = _LINK.search(item)
        if not a:
            continue
        href = html.unescape(a.group(1))
        tertiary = re.search(r"<div class='item__tertiary'>(.*?)</div>", item, re.S)
        out.append({
            "id": owner_from_link(href),
            "name": text_of(a.group(2)),
            "link": href,
            "added": parse_date(tertiary.group(1)) if tertiary else None,
        })
    return out


# ── Фото, видео, документы, музыка ──

def album_list(page: str) -> list[dict]:
    """Альбомы: [{key: '-6' | 'tagged' | '309003426', title, page}]."""
    return [{"key": m.group(1), "title": text_of(m.group(2)), "page": f"photos/photo-albums/{m.group(1)}.html"}
            for m in re.finditer(r'<a href="photo-albums/([^"/]+)\.html">(.*?)</a>', page, re.S)]


def photos_page(page: str) -> list[dict]:
    out = []
    for item in items(page):
        img = re.search(r'<img src="([^"]+)" alt="([^"]*)"', item)
        link = re.search(r'href="(https?://vk\.(?:com|ru)/photo(-?\d+_\d+))"', item)
        if not img and not link:
            continue
        mains = re.findall(r"<div class='item__main'>(.*?)</div>(?=<div class|\s*<div class|\s*$)", item, re.S)
        caption = ""
        for main in mains[1:]:
            t = text_of(main)
            if t and not t.startswith("vk.com/photo"):
                caption = t
                break
        tertiary = re.findall(r"<div class='item__tertiary'>(.*?)</div>", item, re.S)
        url = html.unescape(img.group(1)) if img else ""
        out.append({
            "key": link.group(2) if link else (img.group(2) if img else ""),
            "url": url if is_file_url(url) else None,
            "link": link.group(1) if link else None,
            "text": caption,
            "date": next((d for d in (parse_date(text_of(t)) for t in tertiary) if d), None),
        })
    return out


def video_albums(page: str) -> list[dict]:
    return [{"key": m.group(1), "title": text_of(m.group(2)), "page": f"video/video-albums/{m.group(1)}.html"}
            for m in re.finditer(r'<a href="video-albums/([^"/]+)\.html">(.*?)</a>', page, re.S)]


def videos_page(page: str) -> list[dict]:
    out = []
    for item in items(page):
        link = re.search(r'href="(https?://vk\.(?:com|ru)/video(-?\d+_\d+))"', item)
        if not link:
            continue
        thumb = re.search(r"background-image:\s*url\(([^)]+)\)", item)
        thumb_url = html.unescape(thumb.group(1).strip("'\"")) if thumb else None
        mains = [text_of(x) for x in re.findall(r"<div class='item__main'>(.*?)</div>(?=<div class|\s*$)", item, re.S)]
        title = next((t for t in mains if t and "просмотр" not in t and not t.startswith("vk.com/video")), "")
        dur = re.search(r"(\d+:\d{2}(?::\d{2})?)\s*<span class=\"divider\">", item)
        views = re.search(r"(\d[\d\s]*)\s*просмотр", item)
        tertiary = re.search(r"<div class='item__tertiary'>(.*?)</div>\s*</div>", item, re.S)
        out.append({
            "key": link.group(2),
            "link": link.group(1),
            "title": title,
            "duration": dur.group(1) if dur else "",
            "views": int(re.sub(r"\D", "", views.group(1))) if views else None,
            "thumb_url": thumb_url if is_file_url(thumb_url or "") else None,
            "date": parse_date(text_of(tertiary.group(1))) if tertiary else None,
        })
    return out


def documents_page(page: str) -> list[dict]:
    out = []
    for item in items(page):
        a = _LINK.search(item)
        if not a:
            continue
        tertiary = re.search(r"<div class='item__tertiary'>(.*?)</div>", item, re.S)
        href = html.unescape(a.group(1))
        out.append({"title": text_of(a.group(2)), "link": href,
                    "url": href if is_file_url(href) else None,
                    "date": parse_date(tertiary.group(1)) if tertiary else None})
    return out


def audios_page(page: str) -> list[dict]:
    out = []
    for m in re.finditer(r'audio__title">(.*?)</div>\s*<span class="fl_r audio__duration">(.*?)</span>', page, re.S):
        full = text_of(m.group(1))
        artist, sep, title = full.partition(" — ")
        out.append({"artist": artist if sep else "", "title": title if sep else full,
                    "duration": text_of(m.group(2))})
    return out


# ── Стена и комментарии ──

def wall_page(page: str) -> list[dict]:
    """Записи стены или комментарии: текст, вложения, автор, дата, ссылка, число комментариев."""
    out = []
    for item in items(page):
        link = re.search(r'class="post__link[^"]*" href="([^"]+)"', item)
        if not link:
            continue
        href = html.unescape(link.group(1))
        pid = re.search(r"wall(-?\d+)_(\d+)(?:\?reply=(\d+))?", href)
        main = re.search(r"<div class='item__main'><div>(.*?)</div></div><div class='item__main'>", item, re.S)
        block = main.group(1) if main else ""
        k = block.find('<div class="kludges">')
        text_html, kludges = (block[:k], block[k:]) if k >= 0 else (block, "")
        span = re.search(r"<span>(.*?)</span>", item[link.end():], re.S)
        author_html = span.group(1) if span else ""
        a = _LINK.search(author_html)
        if a:
            author, author_id = text_of(a.group(2)), owner_from_link(a.group(1))
        else:
            author = text_of(re.split(r"\s\d{1,2}\s", author_html, maxsplit=1)[0])
            author_id = None
        comments = re.search(r'href="(\d+/comments\d*\.html)">[^<]*?\((\d+)\)', item)
        post = {
            "id": int(pid.group(3) or pid.group(2)) if pid else 0,
            "post_id": int(pid.group(2)) if pid else 0,
            "owner_id": int(pid.group(1)) if pid else 0,
            "link": href,
            "text": text_of(text_html),
            "author": author,
            "author_id": author_id,
            "out": author == "Вы",
            "date": parse_date(text_of(author_html)) or 0,
            "comments_page": comments.group(1) if comments else None,
            "comments_count": int(comments.group(2)) if comments else 0,
        }
        atts = attachments(kludges)
        if atts:
            post["attachments"] = atts
        out.append(post)
    return out
