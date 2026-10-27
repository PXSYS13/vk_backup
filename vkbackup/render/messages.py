"""Переписки: список бесед и каждая беседа — страницами по 1000 сообщений, как в экспорте Telegram.

Рядом со страницами беседы — messages.txt: та же переписка простым текстом.
"""

from __future__ import annotations

import zlib
from pathlib import Path

from vkbackup.render import att
from vkbackup.render.base import avatar, clock, day, h, page, plural, rel, vk_link, vk_text, when, write
from vkbackup.store import Store

PER_PAGE = 1000
# Сообщения одного человека с разницей меньше 5 минут — одной группой, без повтора имени
JOIN_SECONDS = 300
CHAT_OFFSET = 2_000_000_000


def page_name(n: int) -> str:
    return "messages.html" if n == 1 else f"messages{n}.html"


def render_all(store: Store, root: Path, me_name: str) -> int:
    chats = []
    for conv in store.all("conversation"):
        peer_id = int(conv["peer_id"])
        count = store.message_count(peer_id)
        if not count:
            continue
        first, last = _render_chat(store, root, conv, count, me_name)
        chats.append((last, conv, count, first))
    chats.sort(key=lambda c: c[0], reverse=True)
    items = []
    for last, conv, count, first in chats:
        title = conv.get("title") or str(conv["peer_id"])
        sub = f"{plural(count, 'сообщение', 'сообщения', 'сообщений')} · {day(first)} — {day(last)}"
        items.append(
            f'<a class="item" href="{h(rel(conv["dir"] + "/" + page_name(1), 1))}">{avatar(title, conv["peer_id"])}'
            f'<span class="grow"><span class="name">{h(title)}</span><br><span class="sub">{h(sub)}</span></span>'
            f'<span class="side">{h(when(last))}</span></a>')
    total = sum(c[2] for c in chats)
    body = (f'<div class="crumbs"><a href="../index.html">Архив</a></div>'
            f'<h1>Переписки</h1><p class="muted">{plural(len(chats), "беседа", "беседы", "бесед")}, '
            f'{plural(total, "сообщение", "сообщения", "сообщений")}. Сначала — где писали последними.</p>'
            f'<div class="list">{"".join(items) or "<div class=item>Переписок нет</div>"}</div>')
    write(root / "messages" / "index.html", page("Переписки", body, 1))
    return len(chats)


def _render_chat(store: Store, root: Path, conv: dict, count: int, me_name: str) -> tuple[int, int]:
    peer_id = int(conv["peer_id"])
    folder = conv["dir"]
    title = conv.get("title") or str(peer_id)
    pages = max(1, -(-count // PER_PAGE))
    depth = folder.count("/") + 1
    link = vk_link(peer_id) if peer_id < CHAT_OFFSET else ""
    buf: list[str] = []
    txt: list[str] = [f"Переписка: {title}"] + ([f"Страница в ВК: {link}"] if link else []) + [""]
    n, page_no = 0, 1
    prev: dict | None = None
    last_day = None
    first = last = 0
    for msg in store.messages(peer_id):
        date = int(msg.get("date") or 0)
        first = first or date
        last = max(last, date)
        if n and n % PER_PAGE == 0:
            _write_chat_page(root, folder, title, link, page_no, pages, buf, depth, count)
            buf, page_no, prev, last_day = [], page_no + 1, None, None
        if day(date) != last_day:
            last_day = day(date)
            buf.append(f'<div class="day">{h(last_day)}</div>')
            prev = None
        buf.append(_message(msg, prev, depth, root, me_name))
        txt += _message_txt(msg, root, me_name)
        prev = None if msg.get("service") and not msg.get("text") else msg
        n += 1
    _write_chat_page(root, folder, title, link, page_no, pages, buf, depth, count)
    (root / folder).mkdir(parents=True, exist_ok=True)
    (root / folder / "messages.txt").write_text("\n".join(txt) + "\n", encoding="utf-8")
    return first, last


def _write_chat_page(root: Path, folder: str, title: str, link: str, n: int, pages: int,
                     buf: list[str], depth: int, count: int) -> None:
    pager = ""
    if pages > 1:
        links: list[str] = []
        for i in range(1, pages + 1):
            if i == n:
                links.append(f"<b>{i}</b>")
            elif i in (1, pages) or abs(i - n) <= 3:
                links.append(f'<a href="{page_name(i)}">{i}</a>')
            elif links[-1] != "…":
                links.append("…")
        pager = f'<nav class="pager">Страницы: {"".join(links)}</nav>'
    vk = f' · <a href="{h(link)}" target="_blank" rel="noreferrer noopener">страница в ВК</a>' if link else ""
    body = (f'<div class="crumbs"><a href="{"../" * depth}index.html">Архив</a> / '
            f'<a href="{"../" * (depth - 1)}index.html">Переписки</a></div>'
            f'<header class="chat-head"><div><h1>{h(title)}</h1>'
            f'<div class="tiny">{plural(count, "сообщение", "сообщения", "сообщений")} · '
            f'<a href="messages.txt">текстом</a>{vk}</div></div></header>'
            f'{pager}<div class="history">{"".join(buf)}</div>{pager}')
    write(root / folder / page_name(n), page(title, body, depth))


def _who(msg: dict, me_name: str) -> str:
    return me_name if msg.get("out") and me_name else str(msg.get("from_name") or "")


def _message(msg: dict, prev: dict | None, depth: int, root: Path, me_name: str) -> str:
    date = int(msg.get("date") or 0)
    if msg.get("service") and not msg.get("text") and not msg.get("attachments"):
        return f'<div class="service">{h(msg["service"])} · {h(clock(date))}</div>'
    name = _who(msg, me_name)
    # Цвет кружка — постоянный для человека: по id, а если id нет — по имени
    key = msg.get("from_id") or (0 if msg.get("out") else zlib.crc32(name.encode("utf-8")) % 1000)
    joined = (prev is not None and _who(prev, me_name) == name and bool(prev.get("out")) == bool(msg.get("out"))
              and 0 <= date - int(prev.get("date") or 0) < JOIN_SECONDS)
    inner = ""
    if not joined:
        who = h(name)
        if msg.get("from_id"):
            who = f'<a href="{h(vk_link(int(msg["from_id"])))}" target="_blank" rel="noreferrer noopener">{who}</a>'
        inner += f'<div class="who">{who}</div>'
    if msg.get("text"):
        inner += f'<div class="text">{vk_text(str(msg["text"]))}</div>'
    if msg.get("service"):
        inner += f'<div class="tiny">{h(msg["service"])}</div>'
    inner += att.render(msg.get("attachments"), depth, root)
    edited = '<span class="edited">изменено</span> ' if msg.get("edited") else ""
    side = "out" if msg.get("out") else "in"
    return (f'<div class="msg {side}{" joined" if joined else ""}" id="m{h(msg.get("id"))}">'
            f'{avatar(name, int(key))}<div class="bubble">{inner}'
            f'<span class="time">{edited}{h(clock(date))}</span></div></div>')


def _message_txt(msg: dict, root: Path, me_name: str) -> list[str]:
    head = f"[{when(int(msg.get('date') or 0))}] {_who(msg, me_name)}"
    if msg.get("service") and not msg.get("text") and not msg.get("attachments"):
        return [f"[{when(int(msg.get('date') or 0))}] {msg['service']}"]
    body = str(msg.get("text") or "").split("\n")
    lines = [f"{head}: {body[0]}"] + [f"    {line}" for line in body[1:]]
    lines += [f"    {a}" for a in att.text_summary(msg.get("attachments"), root)]
    return lines
