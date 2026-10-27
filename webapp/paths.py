"""Где лежат файлы программы.

Модули читают пути в момент вызова (paths.SETTINGS_FILE), а не копируют их при импорте:
tests/conftest.py подменяет их на временные, и подмена должна доходить до всех.
"""

from __future__ import annotations

from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = PROJECT / "settings.json"
TEMPLATES_DIR = PROJECT / "webui_assets"
LOG_DIR = PROJECT / "logs"
WEBUI_LOG = LOG_DIR / "webui.log"
DEFAULT_BACKUP_DIR = PROJECT / "backup"
# Где искать архив, который прислал ВК: папка «Загрузки»
DOWNLOADS_DIR = Path.home() / "Downloads"
