"""«Мой ВК в цифрах», «В этот день», поиск по перепискам и просмотр архива через программу."""

import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import webui
from vkbackup import stats
from vkbackup.backup import Backup
from vkbackup.store import DB_NAME, Store
from webapp import api, ports

ALL = ["messages", "friends", "photos", "videos", "wall", "music", "docs"]


@pytest.fixture
def built(archive_zip, tmp_path):
    """Архив, собранный без сети: база и страницы."""
    out = tmp_path / "out"
    b = Backup()
    assert b.start(archive_zip, out, ALL, False)
    b.wait(30)
    assert b.snapshot()["state"] == "done"
    store = Store(out / DB_NAME)
    yield out, store
    store.close()


def test_numbers(built):
    _out, store = built
    s = stats.compute(store)
    assert s["messages"] == 8 and s["sent"] == 3 and s["received"] == 5
    assert [y["year"] for y in s["years"]] == [2014, 2015, 2016]
    assert s["years"][0] == {"year": 2014, "sent": 1, "total": 2}
    assert s["people"][0]["title"] == "Пётр Тестов" and s["people"][0]["count"] == 6
    assert s["groups"][0]["peer_id"] == 2000000001
    assert s["registered"] == "27 мая 2008"
    assert s["kinds"]["photo"] == 1 and s["kinds"]["voice"] == 1
    assert sum(s["hours"]) == 8 and sum(s["weekdays"]) == 8
    first = s["first_message"]
    assert first["text"] == "Привет & пока <b>" and first["out"]
    assert first["page"] == "messages/Пётр Тестов (2002)/messages.html#m100"
    # Годы друзей без пропусков: 2026 — единственный, но ряд всё равно непрерывный
    assert s["friends_by_year"] == [{"year": 2026, "count": 2}]


def test_numbers_without_messages(tmp_path):
    store = Store(tmp_path / DB_NAME)
    try:
        assert stats.compute(store) == {"messages": 0}
        assert stats.search(store, "привет")["hits"] == []
    finally:
        store.close()


def test_on_this_day(built):
    _out, store = built
    now = time.mktime((2017, 1, 2, 12, 0, 0, 0, 0, -1))
    day = stats.on_this_day(store, now)
    assert day["day"] == "02.01"
    assert len(day["messages"]) == 1
    hit = day["messages"][0]
    assert time.localtime(hit["date"]).tm_year == 2015 and hit["that_day"] == 2
    assert hit["page"].endswith(f"#m{hit['id']}")
    # Этот же день, но этого года — не «прошлое»
    assert stats.on_this_day(store, time.mktime((2015, 1, 2, 12, 0, 0, 0, 0, -1)))["messages"] == []


def test_search_ignores_case_and_wildcards(built):
    _out, store = built
    res = stats.search(store, "  ПРИВЕТ ")
    assert res["query"] == "привет"
    assert [h["id"] for h in res["hits"]] == [200, 100]  # новые первыми
    assert res["hits"][1]["page"] == "messages/Пётр Тестов (2002)/messages.html#m100"
    assert stats.search(store, "%")["hits"] == []         # не «всё подряд»
    assert stats.search(store, "_")["hits"] == []
    assert stats.search(store, "в")["hits"] == []         # одна буква — не ищем
    assert stats.search(store, "привет", peer_id=2002)["hits"][0]["id"] == 100


def test_search_points_to_the_right_page(tmp_path, monkeypatch):
    """Беседа больше одной страницы: ссылка ведёт на ту страницу, где лежит сообщение."""
    from vkbackup.render import messages as render_messages
    monkeypatch.setattr(stats, "PER_PAGE", 2)
    monkeypatch.setattr(render_messages, "PER_PAGE", 2)
    store = Store(tmp_path / DB_NAME)
    try:
        store.put("conversation", 7, {"peer_id": 7, "title": "Тест", "dir": "messages/Тест (7)"})
        store.put_messages(7, [{"id": i, "date": 1_500_000_000 + i, "text": f"сообщение {i}"} for i in range(1, 6)])
        hit = stats.search(store, "сообщение 5")["hits"][0]
        assert hit["page"] == "messages/Тест (7)/messages3.html#m5"
    finally:
        store.close()


def test_stats_page_has_no_scripts_and_no_inline_styles(built):
    out, _store = built
    page = (out / "stats" / "index.html").read_text(encoding="utf-8")
    assert "Мой ВКонтакте в цифрах" in page and "Пётр Тестов" in page
    # Странице архива запрещены и скрипты, и атрибут style: графики — атрибутами SVG
    assert "<script" not in page and not re.search(r"\sstyle=", page)
    index = (out / "index.html").read_text(encoding="utf-8")
    assert 'href="stats/index.html"' in index
    for path in out.rglob("*.html"):
        assert not re.search(r"\sstyle=", path.read_text(encoding="utf-8")), path


def test_program_page_has_no_inline_styles():
    """Политика безопасности страницы программы запрещает атрибут style — размеры полос ставит JS."""
    root = Path(__file__).resolve().parent.parent
    assets = root / "webui_assets"
    files = [assets / "app.html", *sorted((assets / "static" / "js").rglob("*.js"))]
    assert len(files) > 1, "скрипты страницы не нашлись"
    for path in files:
        assert not re.search(r"""\sstyle=["'`]""", path.read_text(encoding="utf-8")), path.name


@pytest.fixture
def client(monkeypatch):
    # Свой бэкап на каждый тест: состояние программы не должно перетекать в другие тесты
    monkeypatch.setattr(api, "backup", Backup())
    return TestClient(webui.app, base_url=f"http://127.0.0.1:{ports.PORT}")


def _ready(client, archive_zip, tmp_path):
    settings = {"archive": str(archive_zip), "folder": str(tmp_path / "out"), "sections": ALL, "download": False}
    assert client.post("/api/settings", json=settings).status_code == 200
    assert client.post("/api/start", json={}).json()["ok"]
    api.backup.wait(30)


def test_api_stats_and_search(client, archive_zip, tmp_path):
    assert client.get("/api/stats").status_code == 400  # архива ещё нет
    _ready(client, archive_zip, tmp_path)
    data = client.get("/api/stats").json()
    assert data["messages"] == 8 and "on_this_day" in data
    assert client.get("/api/status").json()["result"]["stats_page"] is True
    hits = client.get("/api/search", params={"q": "Привет"}).json()["hits"]
    assert {h["id"] for h in hits} == {100, 200}


def test_archive_is_viewable_through_the_program(client, archive_zip, tmp_path):
    _ready(client, archive_zip, tmp_path)
    r = client.get("/archive/index.html")
    assert r.status_code == 200 and "Иван Проверкин" in r.text
    assert client.get("/archive/").status_code == 200           # папка → её index.html
    assert client.get("/archive/stats").status_code == 200
    assert client.get("/archive/assets/style.css").headers["content-type"].startswith("text/css")
    assert client.get(f"/archive/{DB_NAME}").status_code == 404  # базу — нет
    for tail in ("-wal", "-shm", "-journal"):  # и её служебные файлы тоже: в них те же сообщения
        side = tmp_path / "out" / f"{DB_NAME}{tail}"
        if not side.exists():
            side.write_bytes(b"x")
        assert client.get(f"/archive/{DB_NAME}{tail}").status_code == 404, tail
    assert client.get("/archive/%2e%2e/settings.json").status_code == 404
    assert client.get("/archive/..%5c..%5cwebui.py").status_code == 404
    assert client.get("/archive/nope.html").status_code == 404
    # Чужой сайт не может даже проверить, есть ли архив
    r = client.get("/archive/index.html", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_attachments_from_people_are_downloaded_not_opened(client, archive_zip, tmp_path):
    """Документ, который прислал собеседник, не должен работать как страница программы:
    открытый с её адреса .html или .svg мог бы читать /api/… от её имени."""
    _ready(client, archive_zip, tmp_path)
    files = tmp_path / "out" / "messages" / "Пётр Тестов (2002)" / "files"
    files.mkdir(parents=True, exist_ok=True)
    for name, body in [("100_1_evil.html", "<script src='100_2_x.js'></script>"),
                       ("100_2_x.js", "fetch('/api/search?q=пароль')"),
                       ("100_3_pic.svg", "<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"),
                       ("100_4_page.htm", "<b>hi</b>"), ("100_5_report.docx", "x"), ("100_6_noext", "x")]:
        (files / name).write_text(body, encoding="utf-8")
        r = client.get(f"/archive/messages/Пётр Тестов (2002)/files/{name}")
        assert r.status_code == 200, name
        assert r.headers["content-disposition"].startswith("attachment"), name
        assert "sandbox" in r.headers["content-security-policy"], name
    # Картинки, голосовые, PDF и текст по-прежнему открываются прямо в браузере
    for name in ("100_7_photo.jpg", "100_8_voice.ogg", "100_9_scan.pdf", "100_10_note.txt"):
        (files / name).write_bytes(b"x")
        r = client.get(f"/archive/messages/Пётр Тестов (2002)/files/{name}")
        assert "content-disposition" not in r.headers, name


def test_every_page_the_program_builds_opens_as_a_page(client, archive_zip, tmp_path):
    _ready(client, archive_zip, tmp_path)
    out = tmp_path / "out"
    pages = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.html"))
    assert len(pages) >= 8
    for rel in pages:
        r = client.get("/archive/" + rel)
        assert r.status_code == 200 and "content-disposition" not in r.headers, rel
        assert r.headers["content-type"].startswith("text/html"), rel
        assert "sandbox" not in r.headers["content-security-policy"], rel


def test_downloader_never_writes_over_a_program_page(tmp_path, monkeypatch):
    """Старая очередь (архив версии 0.2.0) могла сохранить путь docs/index.html: скачанный
    по нему чужой файл открылся бы как страница программы. Загрузчик такой путь не пишет."""
    from vkbackup import media, net
    calls = []
    monkeypatch.setattr(net, "download", lambda url, dest: calls.append(url) or 0)
    store = Store(tmp_path / DB_NAME)
    try:
        for path in ("docs/index.html", "docs/INDEX.HTML", "messages/Анна (5)/messages2.html"):
            store.add_media(path, "https://psv4.userapi.com/x.html", "docs")
        dl = media.Downloader(store, tmp_path)
        dl.start()
        dl.finish()
        dl.join(10)
        assert calls == []
        assert {f["path"] for f in store.failed_media()} == {
            "docs/index.html", "docs/INDEX.HTML", "messages/Анна (5)/messages2.html"}
    finally:
        store.close()
    assert not (tmp_path / "docs" / "index.html").exists()


def test_document_named_like_a_program_page_gets_another_name():
    from vkbackup import importer
    assert importer.doc_file("index.html") != "docs/index.html"
    assert importer.doc_file("INDEX.HTML").lower() != "docs/index.html"
    assert importer.doc_file("отчёт.pdf") == "docs/отчёт.pdf"


def test_retry_now_when_idle(client):
    assert client.post("/api/retry-now", json={}).json()["ok"] is False
