"""Общая настройка тестов: корень проекта в sys.path, изоляция от файлов проекта."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))


@pytest.fixture(autouse=True)
def _isolate_project_files(tmp_path, monkeypatch):
    """Страница программы читает и пишет settings.json и logs/ рядом с программой.

    Тесты не должны ни зависеть от них, ни портить их: подменяем пути на временные.
    """
    import webapp.paths

    monkeypatch.setattr(webapp.paths, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(webapp.paths, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(webapp.paths, "WEBUI_LOG", tmp_path / "logs" / "webui.log")
    monkeypatch.setattr(webapp.paths, "DEFAULT_BACKUP_DIR", tmp_path / "backup")
    monkeypatch.setattr(webapp.paths, "DOWNLOADS_DIR", tmp_path / "Downloads")
    yield


@pytest.fixture
def archive_zip(tmp_path):
    import fake_archive
    return fake_archive.build(tmp_path / "Downloads" / "Archive.zip")
