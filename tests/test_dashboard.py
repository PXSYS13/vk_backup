"""Панель: всё об архиве на одном экране — файлы, причины ошибок, диск, история запусков."""

import pytest
from fastapi.testclient import TestClient

import webui
from vkbackup.backup import Backup
from vkbackup.store import DB_NAME, Store
from webapp import api, dashboard, ports

ALL = ["messages", "friends", "photos", "videos", "wall", "music", "docs"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "backup", Backup())
    return TestClient(webui.app, base_url=f"http://127.0.0.1:{ports.PORT}")


def _ready(client, archive_zip, tmp_path, download=False):
    settings = {"archive": str(archive_zip), "folder": str(tmp_path / "out"), "sections": ALL,
                "download": download}
    assert client.post("/api/settings", json=settings).status_code == 200
    assert client.post("/api/start", json={}).json()["ok"]
    api.backup.wait(30)
    return tmp_path / "out"


@pytest.mark.parametrize(("error", "code"), [
    ("sun9-11.userapi.com ответил 404", "gone"),
    ("psv4.userapi.com ответил 410", "gone"),
    ("sun9-11.userapi.com ответил 403", "gone"),
    ("нет связи с sun9-11.userapi.com: TimeoutError", "network"),
    ("sun9-11.userapi.com: обрыв при скачивании (ConnectionResetError)", "network"),
    ("sun9-11.userapi.com прислал файл не целиком", "network"),
    ("sun9-11.userapi.com ответил 504", "server"),
    ("замок: evil.example не в белом списке", "lock"),
    ("путь вне папки архива", "path"),
    ("имя занято страницей архива", "path"),
    ("адрес не https", "other"),
    (None, "other"),
])
def test_failure_reasons_are_grouped_for_people(error, code):
    assert dashboard.classify(error) == code


def test_reasons_count_and_sort(tmp_path):
    store = Store(tmp_path / DB_NAME)
    try:
        for i, err in enumerate(["a.userapi.com ответил 404", "b.userapi.com ответил 404",
                                 "c.userapi.com ответил 410", "нет связи с a.userapi.com: OSError"]):
            store.add_media(f"photos/{i}.jpg", f"https://a.userapi.com/{i}.jpg", "photos")
            store.media_failed(f"photos/{i}.jpg", err, final=True)
        reasons = dashboard.failure_reasons(store)
    finally:
        store.close()
    assert [(r["code"], r["count"]) for r in reasons] == [("gone", 3), ("network", 1)]
    assert all(r["title"] and r["hint"] for r in reasons)


def test_dashboard_before_any_backup(client):
    data = client.get("/api/dashboard").json()
    assert data["ready"] is False
    assert data["content"] is None and data["runs"] == [] and data["reasons"] == []
    assert data["archive"]["exists"] is False
    assert data["network"]["installed"] is True
    checks = {c["key"]: c for c in data["checks"]}
    assert set(checks) == {"pages", "files", "fresh", "disk", "lock"}
    assert checks["pages"]["ok"] is False and checks["lock"]["ok"] is True


def test_dashboard_after_offline_backup(client, archive_zip, tmp_path):
    out = _ready(client, archive_zip, tmp_path)
    data = client.get("/api/dashboard").json()
    assert data["ready"] is True
    assert data["content"]["messages"] == 8 and data["content"]["friends"] == 2
    assert data["archive"]["exists"] is True and data["archive"]["size"] == archive_zip.stat().st_size
    assert data["archive"]["age_days"] == 0
    assert data["folder"]["path"] == str(out) and data["folder"]["db_bytes"] > 0
    assert data["folder"]["disk_free"] > 0 and data["folder"]["disk_total"] >= data["folder"]["disk_free"]
    checks = {c["key"]: c for c in data["checks"]}
    assert checks["pages"]["ok"] is True and checks["fresh"]["ok"] is True
    # Фото и голосовые не качались — удалять страницу ВК ещё рано
    assert checks["files"]["ok"] is False and "галочк" in checks["files"]["hint"]
    [run] = data["runs"]
    assert run["state"] == "done" and run["download"] is False
    assert run["finished_at"] >= run["started_at"] and run["messages"] == 8


def test_runs_history_keeps_last_ten(client, archive_zip, tmp_path):
    out = _ready(client, archive_zip, tmp_path)
    store = Store(out / DB_NAME)
    try:
        store.set_progress(dashboard.RUNS_KEY, [{"started_at": i, "finished_at": i, "state": "done"}
                                                for i in range(10)])
    finally:
        store.close()
    assert client.post("/api/start", json={}).json()["ok"]
    api.backup.wait(30)
    runs = client.get("/api/dashboard").json()["runs"]
    assert len(runs) == 10
    assert runs[0]["started_at"] > 1_000_000  # новые первыми
    assert runs[-1]["started_at"] == 1        # самый старый вытеснен


def test_failed_files_show_up_with_reasons(client, archive_zip, tmp_path):
    out = _ready(client, archive_zip, tmp_path)
    store = Store(out / DB_NAME)
    try:
        store.add_media("photos/x.jpg", "https://sun9-1.userapi.com/x.jpg", "photos")
        store.media_failed("photos/x.jpg", "sun9-1.userapi.com ответил 404", final=True)
    finally:
        store.close()
    data = client.get("/api/dashboard").json()
    assert data["media"]["photos"]["failed"] == 1
    assert [r["code"] for r in data["reasons"]] == ["gone"]
    assert {c["key"]: c["ok"] for c in data["checks"]}["files"] is False


def test_status_reports_last_run(client, archive_zip, tmp_path):
    _ready(client, archive_zip, tmp_path)
    last = client.get("/api/status").json()["result"]["last_run"]
    assert last["state"] == "done" and last["finished_at"]


def test_chats_for_search_filter(client, archive_zip, tmp_path):
    assert client.get("/api/chats").status_code == 400  # архива ещё нет
    _ready(client, archive_zip, tmp_path)
    chats = client.get("/api/chats").json()["chats"]
    assert chats[0] == {"peer_id": 2002, "title": "Пётр Тестов", "count": 6}
    assert {c["peer_id"] for c in chats} == {2002, 2000000001}


def test_search_limit_and_peer_filter(client, archive_zip, tmp_path):
    _ready(client, archive_zip, tmp_path)
    res = client.get("/api/search", params={"q": "привет", "limit": 1}).json()
    assert len(res["hits"]) == 1 and res["more"] is True
    res = client.get("/api/search", params={"q": "привет", "peer": 2002}).json()
    assert [h["id"] for h in res["hits"]] == [100]
    # Слишком большой или отрицательный предел не роняет программу
    assert client.get("/api/search", params={"q": "привет", "limit": 10_000}).status_code == 200
    assert client.get("/api/search", params={"q": "привет", "limit": -5}).status_code == 200


def test_find_archives_reports_date(client, archive_zip):
    [found] = client.get("/api/find-archives").json()["archives"]
    assert found["modified"] == pytest.approx(archive_zip.stat().st_mtime)


def test_disk_space_check(monkeypatch, tmp_path):
    assert dashboard.disk_check(tmp_path)["ok"] is True
    monkeypatch.setattr(dashboard, "MIN_FREE", 1 << 62)
    check = dashboard.disk_check(tmp_path)
    assert check["ok"] is False and "освободите" in check["hint"].lower()


def test_freshness_check():
    assert dashboard.fresh_check(0)["ok"] is True
    assert dashboard.fresh_check(dashboard.FRESH_DAYS)["ok"] is True
    stale = dashboard.fresh_check(dashboard.FRESH_DAYS + 1)
    assert stale["ok"] is False and "свежий" in stale["hint"]
    assert dashboard.fresh_check(None)["ok"] is False
    # Все файлы уже скачаны — свежий архив больше не нужен, проверка не держит панель «красной» вечно
    assert dashboard.fresh_check(dashboard.FRESH_DAYS + 30, files_done=True)["ok"] is True


def test_pages_check_wants_a_finished_import(tmp_path):
    (tmp_path / "index.html").write_text("ok", encoding="utf-8")
    assert dashboard.pages_check(tmp_path, {"state": "done"}, imported=True)["ok"] is True
    # Остановили посреди разбора: страницы есть, но в них не всё
    stopped = dashboard.pages_check(tmp_path, {"state": "stopped"}, imported=False)
    assert stopped["ok"] is False and "Продолжить" in stopped["hint"]
    assert dashboard.pages_check(tmp_path, {"state": "error"}, imported=True)["ok"] is False
    # Архив из версии без истории запусков: судим по отметке «разобран целиком»
    assert dashboard.pages_check(tmp_path, None, imported=True)["ok"] is True
    assert dashboard.pages_check(tmp_path / "nope", None, imported=True)["ok"] is False


def test_files_check_counts_every_unfinished_state():
    done = {"pending": 0, "waiting": 0, "done": 3, "failed": 0}
    assert dashboard.files_check({"photos": done}, True)["ok"] is True
    for state in ("pending", "waiting", "failed"):
        assert dashboard.files_check({"photos": {**done, state: 1}}, True)["ok"] is False, state
    # Галочка «скачать файлы» снята — файлов нет вовсе, и это не «всё скачано»
    assert dashboard.files_check({}, False)["ok"] is False


def test_files_check_does_not_trust_an_empty_queue():
    done_run = {"state": "done", "download": True}
    # Галочку поставили, а бэкап с ней ещё не запускали: очереди нет, но и файлов нет
    assert dashboard.files_check({}, True)["ok"] is False
    assert dashboard.files_check({}, True, {"state": "done", "download": False})["ok"] is False
    assert dashboard.files_check({}, True, {"state": "stopped", "download": True})["ok"] is False
    # Бэкап с галочкой прошёл до конца, а файлов по ссылкам в архиве не было — всё в порядке
    assert dashboard.files_check({}, True, done_run)["ok"] is True


def test_broken_progress_value_does_not_break_status(client, archive_zip, tmp_path):
    out = _ready(client, archive_zip, tmp_path)
    store = Store(out / DB_NAME)
    try:
        with store.tx() as c:
            c.execute("INSERT OR REPLACE INTO progress(section, value) VALUES (?, ?)", (dashboard.RUNS_KEY, "{bad"))
    finally:
        store.close()
    assert client.get("/api/status").json()["result"]["last_run"] is None
    assert client.get("/api/dashboard").json()["runs"] == []


def test_run_history_replaces_the_same_run(tmp_path):
    store = Store(tmp_path / DB_NAME)
    try:
        store.save_run({"started_at": 5, "state": "running"})
        store.save_run({"started_at": 5, "state": "done", "files": 3})
        store.save_run({"started_at": 9, "state": "running"})
        assert store.runs() == [{"started_at": 9, "state": "running"},
                                {"started_at": 5, "state": "done", "files": 3}]
    finally:
        store.close()


def test_stop_after_the_end_does_not_stick_in_stopping():
    b = Backup()
    b.status.state = "done"
    b._thread = type("Alive", (), {"is_alive": lambda self: True})()  # поток ещё дописывает историю
    b.stop()
    assert b.status.state == "done"
