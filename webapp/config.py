"""Настройки программы: где архив ВК, куда сохранять, что сохранять, качать ли файлы.

Лежат в settings.json рядом с программой. Ни паролей, ни ключей доступа программа не
хранит — они ей не нужны.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from vkbackup.backup import SECTIONS
from webapp import paths


def load() -> dict:
    try:
        data = json.loads(paths.SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    sections = data.get("sections")
    return {
        "archive": str(data.get("archive") or ""),
        "folder": str(data.get("folder") or paths.DEFAULT_BACKUP_DIR),
        "sections": [s for s in sections if s in SECTIONS] if isinstance(sections, list) else list(SECTIONS),
        "download": bool(data.get("download", True)),
    }


def save(archive: str, folder: str, sections: list[str], download: bool) -> dict:
    data = {"archive": archive, "folder": folder,
            "sections": [s for s in SECTIONS if s in sections], "download": bool(download)}
    path: Path = paths.SETTINGS_FILE
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return data
