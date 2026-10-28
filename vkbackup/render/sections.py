"""Страницы архива, кроме переписок: главная, друзья, фото, видео, стена, музыка, файлы."""

from __future__ import annotations

import csv
import io
import shutil
from pathlib import Path

from vkbackup.media import exists
from vkbackup.render import att
from vkbackup.render.base import avatar, ext_link, h, page, plural, rel, vk_text, when, write
from vkbackup.store import Store

STYLE = Path(__file__).with_name("style.css")
WALL_PER_PAGE = 100

TITLES = {"messages": "Переписки", "friends": "Друзья", "photos": "Фото", "videos": "Видео",
          "wall": "Стена", "music": "Музыка", "docs": "Файлы"}


def copy_style(root: Path) -> None:
    (root / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(STYLE, root / "assets" / "style.css")


def _crumbs(depth: int, *trail: tuple[str, str]) -> str:
    links = [f'<a href="{"../" * depth}index.html">Архив</a>']
    links += [f'<a href="{href}">{h(text)}</a>' for href, text in trail]
    return f'<div class="crumbs">{" / ".join(links)}</div>'


def _csv(rows: list[list[object]]) -> str:
    out = io.StringIO()
    csv.writer(out).writerows(rows)
    return out.getvalue()


def me_name(store: Store) -> str:
    return str((store.get("profile", "me") or {}).get("name") or "")


# ── Главная ──

def render_index(store: Store, root: Path, sections: dict[str, str], stats: str | None = None) -> None:
    me = store.get("profile", "me") or {}
    name = me.get("name") or "Мой ВКонтакте"
    uid = int(me.get("id") or 0)
    ava = me.get("avatar_file") if me.get("avatar_file") and exists(root, me["avatar_file"]) else None
    facts = [f"{h(k)}: {h(v)}" for k, v in me.get("info") or []
             if k.lower() in ("дата рождения", "дата регистрации", "город", "родной город") and v]
    cards = []
    for key, title in TITLES.items():
        text = sections.get(key)
        if text is None:
            cards.append(f'<div class="section off"><b>{title}</b><span>нет в архиве</span></div>')
        else:
            cards.append(f'<a class="section" href="{key}/index.html"><b>{title}</b><span>{h(text)}</span></a>')
    link = f"https://vk.com/id{uid}" if uid else ""
    highlight = (f'<a class="section highlight" href="stats/index.html"><b>Мой ВКонтакте в цифрах</b>'
                 f'<span>{h(stats)}: годы, главные собеседники, часы, первое сообщение</span></a>' if stats else "")
    body = (f'<div class="card profile">{avatar(name, uid, ava, 0)}<div>'
            f'<h1>{h(name)}</h1><div class="muted">{ext_link(link, link) if link else ""}</div>'
            f'<div class="tiny">{" · ".join(facts)}</div></div></div>'
            f'{highlight}<div class="sections">{"".join(cards)}</div>'
            f'<div class="card tiny note">Архив целиком лежит в этой папке. '
            f'Все данные в машиночитаемом виде — в файле <code>vk_backup.db</code> (SQLite). '
            f'Страницы открываются без интернета: браузеру запрещено загружать для них что-либо из сети.</div>')
    write(root / "index.html", page(f"Архив ВКонтакте — {name}", body, 0))


# ── Друзья ──

def render_friends(store: Store, root: Path) -> str:
    friends = sorted(store.all("friend"), key=lambda f: str(f.get("name") or "").lower())
    rows = []
    table = [["id", "Имя", "Ссылка", "В друзьях с"]]
    for f in friends:
        fid = int(f.get("id") or 0)
        added = when(int(f["added"])) if f.get("added") else ""
        table.append([fid or "", f.get("name", ""), f.get("link", ""), added])
        rows.append(f'<div class="item">{avatar(f.get("name", ""), fid)}<span class="grow">'
                    f'<span class="name">{h(f.get("name"))}</span><br><span class="sub">'
                    f'{ext_link(f.get("link", ""), f.get("link", ""))}</span></span>'
                    f'<span class="side">{h("в друзьях с " + added[:10] if added else "")}</span></div>')
    folder = root / "friends"
    folder.mkdir(parents=True, exist_ok=True)
    # utf-8-sig — чтобы Excel открыл кириллицу без «кракозябр»
    (folder / "friends.csv").write_text(_csv(table), encoding="utf-8-sig", newline="")
    (folder / "friends.txt").write_text(
        "\n".join(f"{f.get('name', '')} — {f.get('link', '')}" for f in friends) + "\n", encoding="utf-8")
    text = plural(len(friends), "друг", "друга", "друзей")
    body = (_crumbs(1) + f'<h1>Друзья</h1><p class="muted">{text}. Списком: '
            f'<a href="friends.csv">таблица для Excel</a> · <a href="friends.txt">текст</a></p>'
            f'<div class="list">{"".join(rows) or "<div class=item>Список пуст</div>"}</div>')
    write(folder / "index.html", page("Друзья", body, 1))
    return text


# ── Фото ──

def photo_lookup(store: Store, root: Path):
    """Ссылка vk.com/photo123_456 → скачанный файл этого фото из альбомов (или None)."""
    def find(link: str | None) -> str | None:
        if not link or "/photo" not in link:
            return None
        key = link.rsplit("/photo", 1)[-1].split("?", 1)[0]
        photo = store.get("photo", key) or {}
        path = photo.get("file")
        return path if path and exists(root, path) else None
    return find


def render_photos(store: Store, root: Path) -> str:
    albums = sorted(store.all("album"), key=lambda a: int(a.get("order") or 0))
    by_album: dict[str, list[dict]] = {}
    for p in store.all("photo"):
        by_album.setdefault(str(p.get("album")), []).append(p)
    cards = []
    total = saved = 0
    for album in albums:
        items = sorted(by_album.get(str(album["key"]), []), key=lambda p: int(p.get("date") or 0))
        if not items:
            continue
        folder = f"photos/{album['dir']}"
        total += len(items)
        figs = []
        for p in items:
            path = p.get("file")
            caption = h(when(int(p["date"]))) if p.get("date") else ""
            if p.get("text"):
                caption += " · " + h(p["text"])
            if path and exists(root, path):
                saved += 1
                src = h(rel(path, 2))
                figs.append(f'<figure><a href="{src}" target="_blank"><img src="{src}" alt="" loading="lazy"></a>'
                            f'<figcaption>{caption}</figcaption></figure>')
            else:
                link = p.get("link")
                figs.append(f'<figure><div class="missing">не скачалось{" · " + ext_link(link, "в ВК") if link else ""}'
                            f'</div><figcaption>{caption}</figcaption></figure>')
        body = (_crumbs(2, ("../index.html", "Фото")) + f'<h1>{h(album.get("title"))}</h1>'
                f'<p class="muted">{plural(len(items), "фотография", "фотографии", "фотографий")}</p>'
                f'<div class="gallery">{"".join(figs)}</div>')
        write(root / folder / "index.html", page(str(album.get("title")), body, 2, wide=True))
        cover = next((p["file"] for p in reversed(items) if p.get("file") and exists(root, p["file"])), None)
        img = f'<img src="{h(rel(cover, 1))}" alt="" loading="lazy">' if cover else '<span class="noimg"></span>'
        cards.append(f'<a class="album" href="{h(rel(folder + "/index.html", 1))}">{img}'
                     f'<div><b>{h(album.get("title"))}</b><br><span class="tiny">{len(items)}</span></div></a>')
    text = plural(total, "фотография", "фотографии", "фотографий")
    body = (_crumbs(1) + f'<h1>Фото</h1><p class="muted">{text} в {plural(len(cards), "альбоме", "альбомах", "альбомах")}, '
            f'скачано {saved}</p><div class="albums">{"".join(cards)}</div>')
    write(root / "photos" / "index.html", page("Фото", body, 1, wide=True))
    return text


# ── Видео ──

def render_videos(store: Store, root: Path) -> str:
    videos = sorted(store.all("video"), key=lambda v: -int(v.get("date") or 0))
    cards = []
    for v in videos:
        thumb = v.get("thumb_file") if v.get("thumb_file") and exists(root, v["thumb_file"]) else None
        img = f'<img src="{h(rel(thumb, 1))}" alt="" loading="lazy">' if thumb else '<span class="noimg"></span>'
        meta = " · ".join(x for x in (when(int(v["date"])) if v.get("date") else "", v.get("duration") or "",
                                      v.get("album") or "") if x)
        cards.append(f'<a class="album" href="{h(v.get("link"))}" target="_blank" rel="noreferrer noopener">{img}'
                     f'<div><b>{h(v.get("title") or "Без названия")}</b><br><span class="tiny">{h(meta)}</span></div></a>')
    text = plural(len(videos), "видеозапись", "видеозаписи", "видеозаписей")
    body = (_crumbs(1) + f'<h1>Видео</h1><p class="muted">{text}. ВК кладёт в архив только ссылки на видео '
            f'и обложки: сами ролики смотрите в ВК по ссылкам, пока страница не удалена. '
            f'Список ссылок — <a href="videos.txt">текстом</a>.</p>'
            f'<div class="albums">{"".join(cards)}</div>')
    (root / "videos").mkdir(parents=True, exist_ok=True)
    (root / "videos" / "videos.txt").write_text(
        "\n".join(f"{v.get('title') or 'Без названия'} — {v.get('link')}" for v in videos) + "\n", encoding="utf-8")
    write(root / "videos" / "index.html", page("Видео", body, 1, wide=True))
    return text


# ── Стена ──

def render_wall(store: Store, root: Path) -> str:
    posts = sorted(store.all("post"), key=lambda p: -int(p.get("date") or 0))
    me = me_name(store)
    lookup = photo_lookup(store, root)
    pages = max(1, -(-len(posts) // WALL_PER_PAGE))
    for n in range(pages):
        chunk = posts[n * WALL_PER_PAGE:(n + 1) * WALL_PER_PAGE]
        pager = ""
        if pages > 1:
            pager = '<nav class="pager">' + "".join(
                f"<b>{i + 1}</b>" if i == n else f'<a href="{_wall_page(i + 1)}">{i + 1}</a>'
                for i in range(pages)) + "</nav>"
        body = (_crumbs(1) + f'<h1>Стена</h1><p class="muted">{plural(len(posts), "запись", "записи", "записей")}</p>'
                + pager + "".join(_post(p, root, me, lookup) for p in chunk) + pager)
        write(root / "wall" / _wall_page(n + 1), page("Стена", body, 1))
    return plural(len(posts), "запись", "записи", "записей")


def _wall_page(n: int) -> str:
    return "index.html" if n == 1 else f"page{n}.html"


def _author(item: dict, me: str) -> tuple[str, int]:
    name = me if item.get("out") and me else str(item.get("author") or "")
    return name, int(item.get("author_id") or 0)


def _post(post: dict, root: Path, me: str, lookup) -> str:
    name, aid = _author(post, me)
    out = (f'<div class="card post" id="p{h(post.get("id"))}"><div class="head">{avatar(name, aid)}'
           f'<div><b>{h(name)}</b><br><span class="tiny">{h(when(int(post.get("date") or 0)))} · '
           f'{ext_link(post.get("link") or "", "в ВК")}</span></div></div>')
    if post.get("text"):
        out += f'<div class="text">{vk_text(str(post["text"]))}</div>'
    out += att.render(post.get("attachments"), 1, root, lookup)
    comments = post.get("comments") or []
    if comments:
        out += '<div class="comments">' + "".join(_comment(c, root, me, lookup) for c in comments) + "</div>"
    elif post.get("comments_count"):
        out += f'<div class="stats">Комментариев: {int(post["comments_count"])}</div>'
    return out + "</div>"


def _comment(c: dict, root: Path, me: str, lookup) -> str:
    name, aid = _author(c, me)
    return (f'<div class="comment">{avatar(name, aid)}<div><b>{h(name)}</b> '
            f'<span class="tiny">{h(when(int(c.get("date") or 0)))}</span><br>{vk_text(str(c.get("text") or ""))}'
            f'{att.render(c.get("attachments"), 1, root, lookup)}</div></div>')


# ── Музыка ──

def render_music(store: Store, root: Path) -> str:
    tracks = store.all("track")
    table = [["Исполнитель", "Название", "Длительность", "Плейлист"]]
    rows = []
    for t in tracks:
        table.append([t.get("artist", ""), t.get("title", ""), t.get("duration", ""), t.get("album", "")])
        rows.append(f"<tr><td>{h(t.get('artist'))}</td><td>{h(t.get('title'))}</td>"
                    f"<td>{h(t.get('duration'))}</td><td>{h(t.get('album'))}</td></tr>")
    folder = root / "music"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "music.csv").write_text(_csv(table), encoding="utf-8-sig", newline="")
    (folder / "music.txt").write_text(
        "\n".join(f"{t.get('artist', '')} — {t.get('title', '')}" for t in tracks) + "\n", encoding="utf-8")
    text = plural(len(tracks), "трек", "трека", "треков")
    body = (_crumbs(1) + f'<h1>Музыка</h1><p class="muted">{text}. Списком: '
            f'<a href="music.csv">таблица</a> · <a href="music.txt">текст</a>. ВК кладёт в архив только '
            f'названия песен, без файлов, — по этому списку музыку легко перенести в любой другой сервис.</p>'
            f'<table class="grid"><tr><th>Исполнитель</th><th>Название</th><th>Время</th><th>Плейлист</th></tr>'
            f'{"".join(rows)}</table>')
    write(folder / "index.html", page("Музыка", body, 1))
    return text


# ── Файлы (документы) ──

def render_docs(store: Store, root: Path) -> str:
    docs = sorted(store.all("doc"), key=lambda d: -int(d.get("date") or 0))
    rows = []
    for d in docs:
        path = d.get("file") if d.get("file") and exists(root, d["file"]) else None
        title = f'<a href="{h(rel(path, 1))}" target="_blank">{h(d.get("title"))}</a>' if path else h(d.get("title"))
        rows.append(f'<div class="item"><span class="grow"><span class="name">{title}</span><br>'
                    f'<span class="sub">{h(when(int(d["date"])) if d.get("date") else "")}</span></span>'
                    f'<span class="side">{ext_link(d.get("link") or "", "в ВК") if d.get("link") else ""}</span></div>')
    text = plural(len(docs), "файл", "файла", "файлов")
    body = (_crumbs(1) + f'<h1>Файлы</h1><p class="muted">{text}. В разделе «Файлы» ВК даёт в архиве только '
            f'ссылки на свой сайт: скачайте нужное вручную, пока страница не удалена. Файлы, '
            f'которые вы пересылали в переписках, программа скачала — они в папках бесед.</p>'
            f'<div class="list">{"".join(rows)}</div>')
    write(root / "docs" / "index.html", page("Файлы", body, 1))
    return text
