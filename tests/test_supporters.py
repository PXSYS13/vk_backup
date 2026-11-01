"""«Нас поддерживают»: общий список автора, копия которого приходит вместе с программой."""

import json

import pytest
from fastapi.testclient import TestClient

import webui
from vkbackup import supporters
from webapp import paths, ports


def _item(name, amount=100, currency="RUB", day="2026-10-20", message=None):
    return {"name": name, "amount": amount, "currency": currency, "date": day, "message": message}


def test_normalize_drops_junk_and_sorts_newest_first():
    data = supporters.normalize({"updated": "2026-10-30", "supporters": [
        _item("Старый", day="2026-01-01"), "мусор", _item("  Новый​  ", day="2026-10-30"),
        {"name": "", "amount": -5, "currency": "rub", "date": "вчера"}]})
    assert [x["name"] for x in data["supporters"]] == ["Новый", "Старый", supporters.ANONYMOUS]
    assert data["supporters"][2] == {"name": supporters.ANONYMOUS, "amount": None, "currency": "RUB",
                                     "date": None, "message": None}
    assert data["updated"] == "2026-10-30"


def test_people_and_top():
    items = supporters.normalize({"supporters": [
        _item("Анна", 300), _item("анна", 300, day="2026-10-01"), _item("Пётр", 10, "USD"),
        _item("Аноним", 5000), _item("Аноним", 100), _item("Иван", 50)]})["supporters"]
    assert supporters.count_people(items) == 5  # Анна один раз, анонимы — каждый свой
    top = supporters.top_supporters(items)
    assert [p["name"] for p in top] == ["Пётр", "Анна"]  # 900 ₽ по курсу выше 600 ₽; аноним в топ не идёт
    assert top[1]["donations"] == 2 and top[1]["since"] == "2026-10-01"


def test_missing_or_broken_file(tmp_path):
    assert supporters.load_local(tmp_path / "nope.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{не json", encoding="utf-8")
    assert supporters.load_local(bad) is None


def test_bundled_list_is_valid():
    data = supporters.load_local(paths.SUPPORTERS_FILE)
    assert data is not None and isinstance(data["supporters"], list)


@pytest.fixture
def client(monkeypatch, tmp_path):
    path = tmp_path / "supporters.json"
    path.write_text(json.dumps({"updated": "2026-10-30", "supporters": [
        _item("Анна", 700, message="Спасибо!"), _item("Пётр", 50)]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(paths, "SUPPORTERS_FILE", path)
    return TestClient(webui.app, base_url=f"http://127.0.0.1:{ports.PORT}")


def test_api_supporters(client):
    data = client.get("/api/supporters").json()
    assert data["people"] == 2 and data["updated"] == "2026-10-30"
    assert [p["name"] for p in data["top"]] == ["Анна"]
    assert data["supporters"][0]["message"] == "Спасибо!"


def test_api_supporters_without_a_file(client, monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "SUPPORTERS_FILE", tmp_path / "missing.json")
    data = client.get("/api/supporters").json()
    assert data["supporters"] == [] and data["people"] == 0 and data["top"] == []


def test_foreign_site_cannot_read_the_list(client):
    assert client.get("/api/supporters", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
