"""Перенос архива ВК в базу программы и очередь файлов на скачивание.

Каждый раздел архива разбирается parse.py и складывается в базу как есть. Прямые ссылки
на файлы (фото, голосовые, документы, обложки видео) ставятся в очередь: путь, куда лягут
файлы, записывается прямо в объект (поле file), и страницы архива потом берут его оттуда.

Повторный импорт того же или более нового архива ничего не дублирует: записи заменяются
по своим id, а уже скачанные файлы второй раз не качаются.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from vkbackup import parse
from vkbackup.archive import Archive
from vkbackup.files import ext_from_url, safe_name
from vkbackup.store import Store

log = logging.getLogger("vkbackup")

SECTIONS = ("messages", "friends", "photos", "videos", "wall", "music", "docs")


class Cancelled(Exception):
    """Пользователь нажал «Остановить»."""


@dataclass
class Ctx:
    archive: Archive
    store: Store
    sections: tuple[str, ...] = SECTIONS
    download: bool = True   # ставить ли файлы в очередь (без этого — архив без сети вообще)
    cancel: threading.Event = field(default_factory=threading.Event)
    # (раздел, сделано, всего, текст) — строка прогресса в интерфейсе
    report: Callable[[str, int, int | None, str], None] = lambda *a: None

    def check(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()

    def media(self, path: str, url: str | None, section: str) -> str | None:
        """Файл в очередь. Возвращает путь в архиве — его записывают в объект как file."""
        if not url or not self.download:
            return None
        self.store.add_media(path, url, section)
        return path


def import_archive(ctx: Ctx) -> dict[str, int]:
    """Весь архив по разделам. Возвращает, сколько чего нашлось."""
    counts: dict[str, int] = {}
    import_profile(ctx)
    steps = {
        "friends": import_friends, "photos": import_photos, "videos": import_videos,
        "wall": import_wall, "music": import_music, "docs": import_docs, "messages": import_messages,
    }
    for name in ("friends", "photos", "videos", "wall", "music", "docs", "messages"):
        if name in ctx.sections:
            ctx.check()
            counts[name] = steps[name](ctx)
    ctx.store.set_progress("imported_at", int(time.time()))
    ctx.store.set_progress("imported_sections", list(ctx.sections))
    return counts


# ── Профиль ──

def import_profile(ctx: Ctx) -> dict:
    a = ctx.archive
    profile = {"id": a.owner_id(), "name": "", "info": []}
    if a.exists("profile/page-info.html"):
        profile.update(parse.page_info(a.read("profile/page-info.html")))
    if profile.get("avatar_url"):
        profile["avatar_file"] = ctx.media("profile/avatar" + ext_from_url(profile["avatar_url"], ".jpg"),
                                           profile["avatar_url"], "profile")
    ctx.store.put("profile", "me", profile)
    return profile


# ── Друзья ──

def import_friends(ctx: Ctx) -> int:
    friends = []
    for name in ctx.archive.names(r"profile/friends\d+\.html"):
        friends += parse.friends_page(ctx.archive.read(name))
    ctx.store.put_many("friend", ((f["id"] or f["link"], f) for f in friends))
    ctx.report("friends", len(friends), len(friends), f"Друзья: {len(friends)}")
    return len(friends)


# ── Фото ──

def album_dir(album: dict) -> str:
    key = str(album["key"])
    title = safe_name(album.get("title") or "Альбом", 60)
    return title if key.startswith("-") or key == "tagged" else f"{title} ({key})"


def import_photos(ctx: Ctx) -> int:
    a = ctx.archive
    if not a.exists("photos/photo-albums.html"):
        return 0
    albums = parse.album_list(a.read("photos/photo-albums.html"))
    total = 0
    for i, album in enumerate(albums, 1):
        ctx.check()
        folder = album_dir(album)
        photos = []
        # Большие альбомы ВК делит на страницы: -6.html, -6/… — берём все, что относятся к альбому
        pages = [album["page"]] + a.names(rf"photos/photo-albums/{album['key']}/[^/]+\.html")
        for page in pages:
            if a.exists(page):
                photos += parse.photos_page(a.read(page))
        for photo in photos:
            photo["album"] = album["key"]
            if photo.get("url"):
                stamp = time.strftime("%Y-%m-%d", time.localtime(photo["date"])) if photo.get("date") else "без даты"
                photo["file"] = ctx.media(
                    f"photos/{folder}/{stamp}_{photo['key']}{ext_from_url(photo['url'], '.jpg')}",
                    photo["url"], "photos")
        ctx.store.put_many("photo", ((p["key"], p) for p in photos if p.get("key")))
        ctx.store.put("album", album["key"], {**album, "dir": folder, "count": len(photos), "order": i})
        total += len(photos)
        ctx.report("photos", i, len(albums), f"Фото: альбом {i} из {len(albums)}, всего {total}")
    return total


# ── Видео ──

def import_videos(ctx: Ctx) -> int:
    a = ctx.archive
    if not a.exists("video/video-albums.html"):
        return 0
    total = 0
    for i, album in enumerate(parse.video_albums(a.read("video/video-albums.html")), 1):
        ctx.check()
        videos = []
        for page in [album["page"]] + a.names(rf"video/video-albums/{album['key']}/[^/]+\.html"):
            if a.exists(page):
                videos += parse.videos_page(a.read(page))
        for v in videos:
            v["album"] = album["title"]
            if v.get("thumb_url"):
                v["thumb_file"] = ctx.media(f"videos/обложки/{v['key']}.jpg", v["thumb_url"], "videos")
        ctx.store.put_many("video", ((v["key"], v) for v in videos))
        ctx.store.put("video_album", album["key"], {**album, "order": i, "count": len(videos)})
        total += len(videos)
    ctx.report("videos", total, total, f"Видео: {total}")
    return total


# ── Стена ──

def _queue_atts(ctx: Ctx, atts: list | None, folder: str, prefix: str, section: str) -> None:
    """Вложения с прямой ссылкой на файл — в очередь, путь — в само вложение."""
    for n, att in enumerate(atts or [], 1):
        url = att.get("url")
        if not url:
            continue
        kind = att["kind"]
        if kind == "photo":
            path = f"{folder}/photos/{prefix}_{n}{ext_from_url(url, '.jpg')}"
        elif kind == "voice":
            path = f"{folder}/voice_messages/{prefix}_{n}{ext_from_url(url, '.ogg')}"
        else:
            name = url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
            ext = ext_from_url(url, "")
            path = f"{folder}/files/{prefix}_{n}{ext}" if len(name) > 40 or not ext else \
                f"{folder}/files/{prefix}_{n}_{safe_name(name, 60)}"
        att["file"] = ctx.media(path, url, section)


def import_wall(ctx: Ctx) -> int:
    a = ctx.archive
    posts = []
    for name in a.names(r"wall/wall\d+\.html"):
        posts += parse.wall_page(a.read(name))
    for i, post in enumerate(posts, 1):
        ctx.check()
        _queue_atts(ctx, post.get("attachments"), "wall", f"post{post['id']}", "wall")
        comments = []
        if post.get("comments_page"):
            folder = post["comments_page"].split("/", 1)[0]
            for name in a.names(rf"wall/{folder}/comments\d+\.html"):
                comments += parse.wall_page(a.read(name))
            for c in comments:
                _queue_atts(ctx, c.get("attachments"), "wall", f"comment{c['id']}", "wall")
        post["comments"] = comments
        if i % 50 == 0:
            ctx.report("wall", i, len(posts), f"Стена: {i} из {len(posts)}")
    ctx.store.put_many("post", ((f"{p['owner_id']}_{p['id']}", p) for p in posts))
    ctx.report("wall", len(posts), len(posts), f"Стена: {len(posts)}")
    return len(posts)


# ── Музыка и документы ──

def import_music(ctx: Ctx) -> int:
    a = ctx.archive
    tracks = []
    for name in a.names(r"audio/audio-albums/[^/]+/audios\d+\.html"):
        page = a.read(name)
        trail = parse.crumbs(page)
        album = trail[-1] if len(trail) >= 3 else "Моя музыка"
        album_key = name.split("/")[2]
        for t in parse.audios_page(page):
            t["album"] = album
            t["album_key"] = album_key
            tracks.append(t)
    # Ключ — порядок в архиве: одинаковые песни в разных плейлистах — разные записи
    ctx.store.put_many("track", ((f"{t['album_key']}:{i:06d}", t) for i, t in enumerate(tracks)))
    ctx.report("music", len(tracks), len(tracks), f"Музыка: {len(tracks)}")
    return len(tracks)


def import_docs(ctx: Ctx) -> int:
    a = ctx.archive
    if not a.exists("profile/documents.html"):
        return 0
    docs = parse.documents_page(a.read("profile/documents.html"))
    for i, d in enumerate(docs):
        if d.get("url"):
            d["file"] = ctx.media(f"docs/{safe_name(d['title'], 80)}", d["url"], "docs")
    ctx.store.put_many("doc", ((d["link"] or str(i), d) for i, d in enumerate(docs)))
    return len(docs)


# ── Переписки ──

def chat_dir(store: Store, peer_id: int, title: str) -> str:
    """Папка переписки. Запоминается при первом импорте: новое название беседы не плодит папок."""
    key = f"chatdir:{peer_id}"
    folder = store.get_progress(key)
    if not folder:
        folder = f"messages/{safe_name(title or str(peer_id), 60)} ({peer_id})"
        store.set_progress(key, folder)
    return folder


def import_messages(ctx: Ctx) -> int:
    a = ctx.archive
    titles = dict(parse.chat_list(a.read("messages/index-messages.html"))) \
        if a.exists("messages/index-messages.html") else {}
    peers = sorted({n.split("/")[1] for n in a.names(r"messages/-?\d+/messages\d+\.html")},
                   key=lambda p: list(titles).index(p) if p in titles else len(titles))
    total = 0
    for i, peer in enumerate(peers, 1):
        ctx.check()
        peer_id = int(peer)
        pages = a.names(rf"messages/{peer}/messages\d+\.html")
        msgs: list[dict] = []
        title = titles.get(peer, "")
        for name in pages:
            page = a.read(name)
            if not title:
                trail = parse.crumbs(page)
                title = trail[-1] if trail else peer
            msgs += parse.messages_page(page)
        folder = chat_dir(ctx.store, peer_id, title)
        for m in msgs:
            _queue_atts(ctx, m.get("attachments"), folder, str(m["id"]), "messages")
        ctx.store.put_messages(peer_id, msgs)
        ctx.store.put("conversation", peer_id, {"peer_id": peer_id, "title": title, "dir": folder,
                                                "count": len(msgs)})
        total += len(msgs)
        ctx.report("messages", i, len(peers), f"Переписки: {i} из {len(peers)} — «{title}», сообщений всего {total}")
    return total
