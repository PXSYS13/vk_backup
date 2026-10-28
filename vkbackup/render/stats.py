"""Страница «Мой ВК в цифрах»: годы переписки, главные собеседники, часы и дни недели.

Графики — обычные блоки с шириной или высотой в процентах: странице архива скрипты запрещены.
"""

from __future__ import annotations

import time
from pathlib import Path

from vkbackup.render.base import avatar, day, h, page, plural, rel, write
from vkbackup.stats import WEEKDAYS, compute
from vkbackup.store import Store

# Стандартная страница книги в русском издательском деле — 1800 знаков с пробелами
BOOK_PAGE = 1800

KINDS = {"photo": ("фото", "фото", "фото"), "voice": ("голосовое", "голосовых", "голосовых"),
         "sticker": ("стикер", "стикера", "стикеров"), "video": ("видео", "видео", "видео"),
         "file": ("файл", "файла", "файлов"), "call": ("звонок", "звонка", "звонков"),
         "gift": ("подарок", "подарка", "подарков"), "audio": ("песня", "песни", "песен"),
         "link": ("ссылка", "ссылки", "ссылок"), "wall": ("запись со стены", "записи со стены", "записей со стены"),
         "fwd": ("пересланное", "пересланных", "пересланных")}

CHRONO = {"night": ("Сова", "чаще всего вы пишете ночью"),
          "morning": ("Жаворонок", "утром вы пишете больше, чем ночью"),
          "day": ("Дневной человек", "большая часть сообщений — днём и вечером")}


def _num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _kinds_line(kinds: dict) -> list[str]:
    out = []
    for kind, forms in KINDS.items():
        n = int(kinds.get(kind) or 0)
        if n:
            n10, n100 = n % 10, n % 100
            word = forms[0] if n10 == 1 and n100 != 11 else forms[1] if 2 <= n10 <= 4 and not 12 <= n100 <= 14 \
                else forms[2]
            out.append(f"<div class='kind'><b>{_num(n)}</b><span>{h(word)}</span></div>")
    return out


def _track(parts: list[tuple[float, str]], tip: str, height: int = 14) -> str:
    """Полоса на SVG: части слева направо (доля 0–100, класс заливки). Странице архива запрещены
    и скрипты, и атрибут style — размеры задаются атрибутами SVG, а это политика разрешает.
    Конец полосы скруглён на 4px, начало — прямое; между частями просвет 2px цветом фона."""
    shapes, x = [], 0.0
    parts = [(w, c) for w, c in parts if w > 0]
    for i, (w, cls) in enumerate(parts):
        if i:
            shapes.append(f'<rect class="gap" x="{x:.2f}%" width="2" height="{height}" transform="translate(-1 0)"/>')
        if i == len(parts) - 1:
            shapes.append(f'<rect class="{cls}" x="{x:.2f}%" width="{w:.2f}%" height="{height}" rx="4"/>'
                          f'<rect class="{cls}" x="{x:.2f}%" width="{w / 2:.2f}%" height="{height}"/>')
        else:
            shapes.append(f'<rect class="{cls}" x="{x:.2f}%" width="{w:.2f}%" height="{height}"/>')
        x += w
    # Сначала части, потом просветы — поверх
    shapes.sort(key=lambda r: 'class="gap"' in r)
    return (f'<svg class="track" width="100%" height="{height}" role="img" aria-label="{h(tip)}">'
            f'<title>{h(tip)}</title>{"".join(shapes)}</svg>')


def _hbars(rows: list[tuple[str, int, int | None]], peak: int) -> str:
    """Горизонтальные полосы: подпись, полоса, число. Если задано, сколько из них ваших, — полоса
    из двух частей: ваши сообщения и собеседников (числа — в подсказке при наведении)."""
    out = []
    for label, n, mine in rows:
        if mine is None:
            bar = _track([(n * 100 / peak if peak else 0, "s1")], f"{label}: {_num(n)}")
        else:
            theirs = n - mine
            bar = _track([(mine * 100 / peak if peak else 0, "s1"), (theirs * 100 / peak if peak else 0, "s2")],
                         f"{label}: вы — {_num(mine)}, собеседники — {_num(theirs)}")
        out.append(f'<div class="hbar"><span class="lbl">{h(label)}</span>{bar}<span class="val">{_num(n)}</span></div>')
    return "".join(out)


LEGEND = '<div class="legend"><span><i></i>вы</span><span><i class="b"></i>собеседники</span></div>'


def _vbars(values: list[int], labels: list[str], tips: list[str], height: int = 130) -> str:
    """Столбцы на SVG: растут от базовой линии, верх скруглён. Под каждым — невидимая зона
    на всю высоту, чтобы подсказка появлялась не только над самим столбцом."""
    peak = max(values) or 1
    n = len(values)
    slot = 100 / n
    cols = []
    for i, (v, tip) in enumerate(zip(values, tips)):
        hgt = v * 100 / peak
        x = i * slot + slot * 0.18
        w = slot * 0.64
        bar = (f'<rect class="s1" x="{x:.2f}%" y="{100 - hgt:.2f}%" width="{w:.2f}%" height="{hgt:.2f}%" rx="3"/>'
               f'<rect class="s1" x="{x:.2f}%" y="{100 - hgt / 2:.2f}%" width="{w:.2f}%" height="{hgt / 2:.2f}%"/>'
               if v else "")
        cols.append(f'<g><title>{h(tip)}: {_num(v)}</title><rect class="hit" x="{i * slot:.2f}%" y="0" '
                    f'width="{slot:.2f}%" height="100%"/>{bar}</g>')
    axis = "".join(f"<span>{h(lbl)}</span>" for lbl in labels)
    return (f'<svg class="vbars" width="100%" height="{height}" role="img" aria-label="Сообщения по часам">'
            f'{"".join(cols)}<line class="base" x1="0" x2="100%" y1="100%" y2="100%"/></svg>'
            f'<div class="axis">{axis}</div>')


def render_stats(store: Store, root: Path) -> str | None:
    """stats/index.html. Без переписок считать нечего — тогда страницы нет (None)."""
    s = compute(store)
    if not s.get("messages"):
        return None
    first_year = time.localtime(s["first_date"]).tm_year if s.get("first_date") else None
    last_year = time.localtime(s["last_date"]).tm_year if s.get("last_date") else None
    since = f"с {first_year} по {last_year} год" if first_year and first_year != last_year else ""
    pages = s["chars"] // BOOK_PAGE
    chrono, chrono_text = CHRONO[s["chronotype"]]
    tiles = [
        (_num(s["messages"]), f"сообщений {since}".strip()),
        (_num(s["sent"]), "написали вы"),
        (_num(s["words"]), f"слов от вас — это {plural(pages, 'страница', 'страницы', 'страниц')} книги"),
        (plural(len(s["years"]), "год", "года", "лет"), "переписки"),
    ]
    body = ['<div class="crumbs"><a href="../index.html">Архив</a></div>',
            f'<h1>Мой ВКонтакте в цифрах</h1><p class="muted">Всё посчитано по вашему архиву на этом компьютере'
            f'{", дата регистрации — " + h(s["registered"]) if s.get("registered") else ""}.</p>',
            '<div class="tiles">' + "".join(f'<div class="tile"><b>{v}</b><span>{h(t)}</span></div>'
                                            for v, t in tiles) + "</div>"]

    years = s["years"]
    peak = max((y["total"] for y in years), default=0)
    best = max(years, key=lambda y: y["total"]) if years else None
    body.append(f'<div class="card"><h2>Переписка по годам</h2><p class="tiny">'
                f'{"Самый разговорчивый год — " + str(best["year"]) + "." if best else ""}</p>{LEGEND}'
                + _hbars([(str(y["year"]), y["total"], y["sent"]) for y in years], peak) + "</div>")

    people = s["people"]
    if people:
        rows = []
        top = people[0]["count"]
        for i, p in enumerate(people, 1):
            link = h(rel(p["dir"] + "/messages.html", 1)) if p.get("dir") else ""
            name = f'<a href="{link}">{h(p["title"])}</a>' if link else h(p["title"])
            since_p = f'с {day(int(p["first"]))}' if p.get("first") else ""
            rows.append(f'<div class="person"><span class="rank">{i}</span>{avatar(p["title"], int(p["peer_id"]))}'
                        f'<span class="grow"><span class="name">{name}</span>'
                        + _track([(p["sent"] * 100 / top, "s1"), ((p["count"] - p["sent"]) * 100 / top, "s2")],
                                 f'вы — {_num(p["sent"])}, {p["title"]} — {_num(p["count"] - p["sent"])}', 10)
                        + f'<span class="tiny">{plural(p["count"], "сообщение", "сообщения", "сообщений")} · '
                        f'{h(since_p)}</span></span></div>')
        body.append('<div class="card"><h2>С кем вы переписывались больше всего</h2>' + LEGEND
                    + "".join(rows) + "</div>")
    groups = s["groups"]
    if groups:
        body.append('<div class="card"><h2>Самые живые беседы</h2>' + LEGEND
                    + _hbars([(g["title"], g["count"], g["sent"]) for g in groups], groups[0]["count"]) + "</div>")

    hours = s["hours"]
    body.append(f'<div class="card"><h2>Когда вы пишете</h2><p class="muted"><b>{h(chrono)}</b>: {h(chrono_text)}. '
                f'Самый активный час — {hours.index(max(hours)):02d}:00.</p>'
                + _vbars(hours, [f"{i:02d}" if i % 3 == 0 else "" for i in range(24)],
                         [f"{i:02d}:00–{i:02d}:59" for i in range(24)]) + "</div>")
    wd = s["weekdays"]
    body.append('<div class="card"><h2>Дни недели</h2>'
                + _hbars([(d, n, None) for d, n in zip(WEEKDAYS, wd)], max(wd)) + "</div>")

    facts = []
    fm = s.get("first_message")
    if fm:
        link = f' · <a href="{h(rel(fm["page"], 1))}">открыть</a>' if fm.get("page") else ""
        who = "вы" if fm["out"] else fm["from"] or fm["chat"]
        facts.append(f'<div class="fact"><span class="tiny">Самое первое сообщение в архиве · {h(day(fm["date"]))}'
                     f'{link}</span><blockquote>{h(fm["text"][:400])}</blockquote>'
                     f'<span class="tiny">{h(who)} — в переписке «{h(fm["chat"])}»</span></div>')
    if s.get("busiest"):
        y, m, d = s["busiest"]["day"].split("-")
        when_ = day(int(time.mktime((int(y), int(m), int(d), 12, 0, 0, 0, 0, -1))))
        facts.append(f'<div class="fact"><span class="tiny">Самый разговорчивый день</span>'
                     f'<b class="big">{h(when_)}</b><span class="tiny">'
                     f'{plural(s["busiest"]["count"], "сообщение", "сообщения", "сообщений")} за один день</span></div>')
    if facts:
        body.append('<div class="facts">' + "".join(facts) + "</div>")
    kinds = _kinds_line(s["kinds"])
    if kinds:
        body.append('<div class="card"><h2>Что ещё было в переписках</h2><div class="kinds">' + "".join(kinds)
                    + "</div></div>")
    for key, title in (("friends_by_year", "Новые друзья по годам"), ("photos_by_year", "Фото в альбомах по годам")):
        rows = s[key]
        if rows:
            body.append(f'<div class="card"><h2>{title}</h2>'
                        + _hbars([(str(r["year"]), r["count"], None) for r in rows], max(r["count"] for r in rows))
                        + "</div>")
    write(root / "stats" / "index.html", page("Мой ВКонтакте в цифрах", "".join(body), 1))
    return f"{plural(s['messages'], 'сообщение', 'сообщения', 'сообщений')} за {plural(len(years), 'год', 'года', 'лет')}"
