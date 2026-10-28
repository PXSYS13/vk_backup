"""«Мой ВК в цифрах», «В этот день» и поиск по перепискам — всё из базы, без сети.

Считает SQL прямо по JSON сообщений (json_extract), поэтому даже сотни тысяч сообщений —
это секунды. Время — местное, как на страницах архива.
"""

from __future__ import annotations

import json
import time

from vkbackup.render.messages import CHAT_OFFSET, PER_PAGE, page_name
from vkbackup.store import Store

WEEKDAYS = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
_LOCAL = "'unixepoch', 'localtime'"
_TEXT = "json_extract(data, '$.text')"
_OUT = "COALESCE(json_extract(data, '$.out'), 0)"


def _titles(store: Store) -> dict[int, dict]:
    return {int(c["peer_id"]): c for c in store.all("conversation")}


def _registered(store: Store) -> str:
    me = store.get("profile", "me") or {}
    return next((v for k, v in me.get("info") or [] if k.lower() == "дата регистрации" and v), "")


def compute(store: Store) -> dict:
    """Всё для экрана «Мой ВК в цифрах» и страницы stats/index.html."""
    q = store.query
    total, sent, first, last = q(f"SELECT COUNT(*), COALESCE(SUM({_OUT}), 0), MIN(NULLIF(date, 0)), "
                                 f"MAX(date) FROM messages")[0]
    if not total:
        return {"messages": 0}
    words, chars = q(
        f"SELECT COALESCE(SUM(LENGTH(t) - LENGTH(REPLACE(REPLACE(t, char(10), ' '), ' ', '')) + 1), 0), "
        f"COALESCE(SUM(LENGTH(t)), 0) FROM (SELECT TRIM({_TEXT}) AS t FROM messages WHERE {_OUT} = 1) "
        f"WHERE t != ''")[0]
    by_year = {int(y): (int(s or 0), n)
               for y, s, n in q(f"SELECT strftime('%Y', date, {_LOCAL}) AS y, SUM({_OUT}), COUNT(*) FROM messages "
                                f"WHERE date > 0 GROUP BY y")}
    years = [{"year": y, "sent": by_year.get(y, (0, 0))[0], "total": by_year.get(y, (0, 0))[1]}
             for y in range(min(by_year), max(by_year) + 1)] if by_year else []
    hours = [0] * 24
    for hh, n in q(f"SELECT CAST(strftime('%H', date, {_LOCAL}) AS INTEGER) AS hh, COUNT(*) FROM messages "
                   f"WHERE date > 0 GROUP BY hh"):
        hours[int(hh)] = n
    weekdays = [0] * 7
    for wd, n in q(f"SELECT CAST(strftime('%w', date, {_LOCAL}) AS INTEGER) AS wd, COUNT(*) FROM messages "
                   f"WHERE date > 0 GROUP BY wd"):
        weekdays[(int(wd) + 6) % 7] = n  # в SQLite неделя с воскресенья, у нас — с понедельника
    titles = _titles(store)

    def peers(where: str, limit: int) -> list[dict]:
        out = []
        for peer_id, n, s, f, la in q(
                f"SELECT peer_id, COUNT(*) AS n, SUM({_OUT}), MIN(NULLIF(date, 0)), MAX(date) FROM messages "
                f"WHERE {where} GROUP BY peer_id ORDER BY n DESC LIMIT ?", (limit,)):
            conv = titles.get(int(peer_id), {})
            out.append({"peer_id": peer_id, "title": conv.get("title") or str(peer_id), "dir": conv.get("dir"),
                        "count": n, "sent": int(s or 0), "first": f, "last": la})
        return out

    busiest = q(f"SELECT strftime('%Y-%m-%d', date, {_LOCAL}) AS d, COUNT(*) AS n FROM messages "
                f"WHERE date > 0 GROUP BY d ORDER BY n DESC LIMIT 1")
    kinds = dict(q("SELECT json_extract(j.value, '$.kind') AS k, COUNT(*) FROM messages, "
                   "json_each(messages.data, '$.attachments') AS j GROUP BY k"))
    night = sum(hours[0:5])
    morning = sum(hours[5:11])
    return {
        "messages": total,
        "sent": int(sent),
        "received": total - int(sent),
        "chats": store.count("conversation"),
        "words": int(words),
        "chars": int(chars),
        "first_date": first,
        "last_date": last,
        "registered": _registered(store),
        "years": years,
        "hours": hours,
        "weekdays": weekdays,
        "people": peers(f"peer_id > 0 AND peer_id < {CHAT_OFFSET}", 10),
        "groups": peers(f"peer_id >= {CHAT_OFFSET}", 5),
        "busiest": {"day": busiest[0][0], "count": busiest[0][1]} if busiest else None,
        "kinds": {k: n for k, n in kinds.items() if k},
        "chronotype": "night" if night > morning else "morning" if morning > night * 2 else "day",
        "first_message": _first_message(store, titles),
        "friends_by_year": _by_year(store, "friend", "added"),
        "photos_by_year": _by_year(store, "photo", "date"),
        "friends": store.count("friend"),
        "photos": store.count("photo"),
        "posts": store.count("post"),
        "tracks": store.count("track"),
    }


def _first_message(store: Store, titles: dict[int, dict]) -> dict | None:
    rows = store.query("SELECT peer_id, id, date, data FROM messages WHERE date > 0 "
                       f"AND TRIM(COALESCE({_TEXT}, '')) != '' ORDER BY date, id LIMIT 1")
    if not rows:
        return None
    peer_id, mid, date, data = rows[0]
    return _hit(store, titles, peer_id, mid, date, json.loads(data))


def _by_year(store: Store, kind: str, field: str) -> list[dict]:
    rows = store.query(f"SELECT strftime('%Y', CAST(json_extract(data, '$.{field}') AS INTEGER), {_LOCAL}) AS y, "
                       f"COUNT(*) FROM objects WHERE kind=? AND CAST(json_extract(data, '$.{field}') AS INTEGER) > 0 "
                       f"GROUP BY y ORDER BY y", (kind,))
    counts = {int(y): n for y, n in rows if y}
    # Год без событий — тоже год: пропуск в ряду лет читался бы как «так и было подряд»
    return [{"year": y, "count": counts.get(y, 0)} for y in range(min(counts), max(counts) + 1)] if counts else []


def _page_of(store: Store, peer_id: int, mid: int) -> int:
    """На какой странице беседы лежит сообщение: страницы по PER_PAGE, по порядку id."""
    before = store.query("SELECT COUNT(*) FROM messages WHERE peer_id=? AND id < ?", (peer_id, mid))[0][0]
    return before // PER_PAGE + 1


def _hit(store: Store, titles: dict[int, dict], peer_id: int, mid: int, date: int, msg: dict) -> dict:
    conv = titles.get(int(peer_id), {})
    folder = conv.get("dir")
    return {
        "peer_id": peer_id,
        "id": mid,
        "date": date,
        "chat": conv.get("title") or str(peer_id),
        "out": bool(msg.get("out")),
        "from": msg.get("from_name") or "",
        "text": str(msg.get("text") or ""),
        "kinds": [a.get("kind") for a in msg.get("attachments") or []],
        "page": f"{folder}/{page_name(_page_of(store, peer_id, mid))}#m{mid}" if folder else None,
    }


def on_this_day(store: Store, now: float | None = None, limit: int = 6) -> dict:
    """Сообщения и фото этого дня прошлых лет: по одному самому содержательному сообщению за год."""
    t = time.localtime(now if now is not None else time.time())
    md, year = f"{t.tm_mon:02d}-{t.tm_mday:02d}", str(t.tm_year)
    titles = _titles(store)
    picked: dict[str, tuple] = {}
    counts: dict[str, int] = {}
    for peer_id, mid, date, data, y in store.query(
            f"SELECT peer_id, id, date, data, strftime('%Y', date, {_LOCAL}) AS y FROM messages "
            f"WHERE date > 0 AND strftime('%m-%d', date, {_LOCAL}) = ? AND y < ? ORDER BY date", (md, year)):
        counts[y] = counts.get(y, 0) + 1
        text = str(json.loads(data).get("text") or "").strip()
        # Лучше всего вспоминается фраза средней длины: не «ок» и не простыня
        score = min(len(text), 160) - max(0, len(text) - 400) / 4
        if text and (y not in picked or score > picked[y][0]):
            picked[y] = (score, peer_id, mid, date, data)
    messages = []
    for y in sorted(picked, reverse=True)[:limit]:
        _score, peer_id, mid, date, data = picked[y]
        hit = _hit(store, titles, peer_id, mid, date, json.loads(data))
        hit["that_day"] = counts[y]
        messages.append(hit)
    photos = []
    for (data,) in store.query(
            f"SELECT data FROM objects WHERE kind='photo' AND json_extract(data, '$.date') > 0 "
            f"AND strftime('%m-%d', CAST(json_extract(data, '$.date') AS INTEGER), {_LOCAL}) = ? "
            f"AND strftime('%Y', CAST(json_extract(data, '$.date') AS INTEGER), {_LOCAL}) < ? "
            f"ORDER BY json_extract(data, '$.date') DESC LIMIT 12", (md, year)):
        p = json.loads(data)
        if p.get("file"):
            photos.append({"file": p["file"], "date": int(p["date"]), "text": p.get("text") or ""})
    return {"day": f"{t.tm_mday:02d}.{t.tm_mon:02d}", "messages": messages, "photos": photos}


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search(store: Store, text: str, limit: int = 100, peer_id: int | None = None) -> dict:
    """Сообщения, где встречается text (без учёта регистра), — новые первыми."""
    needle = " ".join(text.split()).lower()
    if len(needle) < 2:
        return {"query": needle, "hits": [], "more": False}
    where = f"ulower({_TEXT}) LIKE ? ESCAPE '\\'"
    params: tuple = (_like(needle),)
    if peer_id is not None:
        where += " AND peer_id = ?"
        params += (peer_id,)
    rows = store.query(f"SELECT peer_id, id, date, data FROM messages WHERE {where} "
                       f"ORDER BY date DESC, id DESC LIMIT ?", params + (limit + 1,))
    titles = _titles(store)
    hits = [_hit(store, titles, p, m, d, json.loads(data)) for p, m, d, data in rows[:limit]]
    return {"query": needle, "hits": hits, "more": len(rows) > limit}
