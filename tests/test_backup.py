"""Весь путь: архив ВК → база → файлы → страницы. Сеть подменена: тесты в интернет не ходят."""

import csv
import re
from pathlib import Path

import fake_archive
import pytest

from vkbackup import media, net
from vkbackup.backup import Backup, render_archive
from vkbackup.store import DB_NAME, Store

ALL = ["messages", "friends", "photos", "videos", "wall", "music", "docs"]


@pytest.fixture
def fake_net(monkeypatch):
    """net.download пишет в файл адрес вместо содержимого; 404 — для адресов с «missing»."""
    calls = []

    def download(url, dest: Path):
        calls.append(url)
        if "missing" in url:
            raise net.NetError("sun9-1.userapi.com ответил 404", 404, "sun9-1.userapi.com")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(url.encode())
        return len(url)

    monkeypatch.setattr(net, "download", download)
    monkeypatch.setattr("vkbackup.firewall.installed", lambda: True)
    return calls


def run(archive, out, download=True, sections=ALL):
    b = Backup()
    assert b.start(archive, out, sections, download)
    b.wait(30)
    return b.snapshot()


def test_offline_run_builds_pages_without_network(archive_zip, tmp_path, monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("без галочки «Скачать файлы» сети быть не должно")
    monkeypatch.setattr(net, "download", no_network)
    out = tmp_path / "out"
    snap = run(archive_zip, out, download=False)
    assert snap["state"] == "done", snap
    assert snap["counts"] == {"friends": 2, "photos": 2, "videos": 1, "wall": 2, "music": 2, "docs": 1,
                              "messages": 8}
    for page in ("index.html", "messages/index.html", "friends/index.html", "photos/index.html",
                 "videos/index.html", "wall/index.html", "music/index.html", "docs/index.html", "assets/style.css"):
        assert (out / page).exists(), page
    store = Store(out / DB_NAME)
    try:
        assert store.media_stats() == {}
    finally:
        store.close()


def test_full_run_downloads_and_links_files(archive_zip, tmp_path, fake_net):
    out = tmp_path / "out"
    snap = run(archive_zip, out)
    assert snap["state"] == "done", snap
    # Фото альбомов, фото и голосовое из переписки, документ, обложка видео, аватарка
    assert fake_archive.VOICE_URL in fake_net and fake_archive.DOC_URL in fake_net
    assert fake_archive.THUMB_URL in fake_net and fake_archive.AVATAR_URL in fake_net
    assert not any("vk.com" in u.split("/")[2] for u in fake_net)  # сайт ВК — никогда
    chat = out / "messages" / "Пётр Тестов (2002)"
    page = (chat / "messages.html").read_text(encoding="utf-8")
    assert 'src="photos/105_1.jpg"' in page.replace("../../messages/Пётр Тестов (2002)/", "")
    assert "voice_messages/103_1.ogg" in page and "<audio" in page
    assert "ВК не кладёт пересланные сообщения в архив" in page
    assert "изменено" in page
    # Порядок — от старых к новым, разбивка по дням
    assert page.index("Привет &amp; пока") < page.index("исправленное")
    assert page.count('class="day"') == 4
    txt = (chat / "messages.txt").read_text(encoding="utf-8")
    assert "Иван Проверкин: Привет & пока <b>" in txt
    # Фото со стены нашлось в альбоме «Фото на стене» по ссылке vk.com/photo…
    wall = (out / "wall" / "index.html").read_text(encoding="utf-8")
    assert "photos/Фото на стене/2014-05-07_1001_9002.jpg" in wall
    assert "Классное фото" in wall


def test_rerun_does_not_download_again(archive_zip, tmp_path, fake_net):
    out = tmp_path / "out"
    run(archive_zip, out)
    first = len(fake_net)
    snap = run(archive_zip, out)
    assert snap["state"] == "done"
    assert len(fake_net) == first


def test_failed_files_are_reported_and_retryable(archive_zip, tmp_path, fake_net, monkeypatch):
    monkeypatch.setattr(fake_archive, "PHOTO_URL", fake_archive.PHOTO_URL + "&missing=1")
    z = fake_archive.build(tmp_path / "broken.zip")
    out = tmp_path / "out"
    assert run(z, out)["state"] == "done"
    store = Store(out / DB_NAME)
    try:
        failed = store.failed_media()
        assert failed and all("404" in f["error"] for f in failed)
        assert store.retry_failed_media() == len(failed)
    finally:
        store.close()
    page = (out / "photos" / "Море_ 2014_ (555)" / "index.html").read_text(encoding="utf-8")
    assert "не скачалось" in page


def test_pages_never_load_anything_from_internet(archive_zip, tmp_path, fake_net):
    out = tmp_path / "out"
    run(archive_zip, out)
    pages = list(out.rglob("*.html"))
    assert len(pages) > 8
    for p in pages:
        text = p.read_text(encoding="utf-8")
        assert 'http-equiv="Content-Security-Policy"' in text, p
        assert "script-src 'none'" in text and "connect-src 'none'" in text
        assert "<script" not in text.lower(), p
        # Всё, что страница загружает сама (src, stylesheet), — только из папки архива
        for attr in re.findall(r'(?:src|href)="([^"]+)"', text):
            if attr.startswith("http"):
                assert re.search(rf'<a [^>]*href="{re.escape(attr)}"', text), (p, attr)


def test_friends_and_music_tables(archive_zip, tmp_path, fake_net):
    out = tmp_path / "out"
    run(archive_zip, out)
    rows = list(csv.reader((out / "friends" / "friends.csv").read_text(encoding="utf-8-sig").splitlines()))
    assert rows[0][:3] == ["id", "Имя", "Ссылка"]
    assert ["2002", "Пётр Тестов", "https://vk.com/id2002"] == rows[2][:3] or \
        ["2002", "Пётр Тестов", "https://vk.com/id2002"] == rows[1][:3]
    assert "Кино — Группа крови" in (out / "music" / "music.txt").read_text(encoding="utf-8")
    assert "https://vk.com/video1001_5" in (out / "videos" / "videos.txt").read_text(encoding="utf-8")


def test_render_again_from_db_only(archive_zip, tmp_path, fake_net):
    out = tmp_path / "out"
    run(archive_zip, out)
    (out / "index.html").unlink()
    store = Store(out / DB_NAME)
    try:
        sections = render_archive(store, out)
    finally:
        store.close()
    assert (out / "index.html").exists()
    assert set(sections) == set(ALL)


def test_downloader_refuses_paths_outside_archive(tmp_path, fake_net):
    store = Store(tmp_path / DB_NAME)
    try:
        store.add_media("../evil.jpg", fake_archive.PHOTO_URL, "photos")
        store.add_media("photos/ok.jpg", fake_archive.PHOTO_URL, "photos")
        d = media.Downloader(store, tmp_path / "root", workers=2)
        d.start()
        d.finish()
        d.join(10)
        assert not (tmp_path / "evil.jpg").exists()
        assert (tmp_path / "root" / "photos" / "ok.jpg").exists()
        assert store.failed_media()[0]["error"] == "путь вне папки архива"
    finally:
        store.close()


def test_disk_error_stops_backup(archive_zip, tmp_path, monkeypatch):
    monkeypatch.setattr("vkbackup.firewall.installed", lambda: True)

    def full_disk(url, dest):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(net, "download", full_disk)
    snap = run(archive_zip, tmp_path / "out")
    assert snap["state"] == "error" and snap["problem"] == "disk"


def test_not_an_archive_is_explained(tmp_path):
    (tmp_path / "x.zip").write_bytes(b"nope")
    snap = run(tmp_path / "x.zip", tmp_path / "out", download=False)
    assert snap["state"] == "error" and snap["problem"] == "archive"
