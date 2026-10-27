"""Страница программы: настройки, запуск, защита от чужих сайтов."""

import time

import pytest
from fastapi.testclient import TestClient

import webui
from webapp import api, config, ports


@pytest.fixture
def client():
    return TestClient(webui.app, base_url=f"http://127.0.0.1:{ports.PORT}")


def _settings(archive, folder, **extra):
    return {"archive": str(archive), "folder": str(folder), "sections": ["messages", "friends"],
            "download": False, **extra}


def test_status_and_security_headers(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert data["network"]["installed"] is True  # webui.py ставит замок при импорте
    assert "userapi.com" in data["network"]["allowed_domains"]
    assert data["job"]["state"] == "idle"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["referrer-policy"] == "no-referrer"


def test_page_and_static(client):
    r = client.get("/")
    assert r.status_code == 200 and "Бэкап ВКонтакте" in r.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/docs").status_code == 404


def test_settings_validation(client, archive_zip, tmp_path):
    r = client.post("/api/settings", json=_settings(tmp_path / "nope.zip", tmp_path / "out"))
    assert r.status_code == 400
    r = client.post("/api/settings", json=_settings(archive_zip, "relative/path"))
    assert r.status_code == 400
    r = client.post("/api/settings", json=_settings(archive_zip, tmp_path / "out", sections=[]))
    assert r.status_code == 400
    r = client.post("/api/settings", json=_settings(archive_zip, tmp_path / "out"))
    assert r.status_code == 200 and r.json()["ok"]
    assert "id1001" in r.json()["msg"]
    assert config.load()["sections"] == ["messages", "friends"]


def test_program_folder_is_refused(client, archive_zip):
    from webapp import paths
    r = client.post("/api/settings", json=_settings(archive_zip, paths.PROJECT / "vkbackup" / "x"))
    assert r.status_code == 400


def test_find_archives_in_downloads(client, archive_zip, tmp_path):
    (tmp_path / "Downloads" / "other.zip").write_bytes(b"not a zip")
    r = client.get("/api/find-archives")
    assert [a["path"] for a in r.json()["archives"]] == [str(archive_zip)]


def test_start_offline_and_result(client, archive_zip, tmp_path):
    client.post("/api/settings", json=_settings(archive_zip, tmp_path / "out"))
    assert client.post("/api/start", json={}).json()["ok"]
    api.backup.wait(30)
    data = client.get("/api/status").json()
    assert data["job"]["state"] == "done", data["job"]
    assert data["result"]["messages"] == 8 and data["result"]["friends"] == 2
    assert data["result"]["name"] == "Иван Проверкин"
    assert client.post("/api/render", json={}).json()["ok"]


def test_foreign_sites_are_refused(client):
    assert client.get("/api/status", headers={"Host": "evil.example:8020"}).status_code == 403
    r = client.post("/api/stop", json={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.get("/api/status", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_security_lists_code_fingerprints(client):
    data = client.get("/api/security").json()
    paths = {c["path"] for c in data["code"]}
    assert {"vkbackup/firewall.py", "vkbackup/net.py", "webui.py"} <= paths
    assert all(len(c["sha256"]) == 64 for c in data["code"])


def test_stop_is_harmless_when_idle(client):
    assert client.post("/api/stop", json={}).json()["ok"]
    time.sleep(0)
