"""Скрипты страницы без браузера: синтаксис, обработчик у каждой кнопки, ссылки на статику."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import webui
from webapp import paths, ports

ASSETS = Path(paths.TEMPLATES_DIR)
APP_HTML = ASSETS / "app.html"
JS_FILES = sorted((ASSETS / "static" / "js").rglob("*.js"))


def _all_js() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in JS_FILES)


def test_scripts_are_split_by_screen():
    names = {p.name for p in JS_FILES}
    assert {"core.js", "main.js", "home.js", "dashboard.js", "setup.js", "search.js"} <= names
    # Каждый файл — в пределах читаемого размера
    assert all(len(p.read_text(encoding="utf-8").splitlines()) < 800 for p in JS_FILES)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js не установлен")
@pytest.mark.parametrize("path", JS_FILES, ids=lambda p: p.name)
def test_js_syntax(path):
    res = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    assert res.returncode == 0, res.stderr


def test_every_button_action_has_a_handler():
    text = APP_HTML.read_text(encoding="utf-8") + _all_js()
    used = set(re.findall(r'data-act="([a-z0-9-]+)"', text))
    registered = set(re.findall(r"onAct\('([a-z0-9-]+)'", _all_js()))
    assert used, "на странице нет ни одной кнопки"
    assert not sorted(used - registered), f"кнопки без обработчика: {sorted(used - registered)}"
    assert not sorted(registered - used), f"обработчики без кнопки: {sorted(registered - used)}"


def test_every_screen_has_a_route_and_a_menu_item():
    html = APP_HTML.read_text(encoding="utf-8")
    screens = set(re.findall(r'id="screen-([a-z]+)"', html))
    menu = set(re.findall(r'data-route="([a-z]+)"', html))
    assert screens == menu
    routes = re.search(r"const ROUTES = \[([^\]]+)\]", _all_js()).group(1)
    assert screens == set(re.findall(r"'([a-z]+)'", routes))


def test_static_references_exist_and_have_proper_types():
    html = APP_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'(?:src|href)="(/static/[^"?]+)', html)
    assert len(refs) >= len(JS_FILES) + 2  # скрипты, стили, тема, значок
    client = TestClient(webui.app, base_url=f"http://127.0.0.1:{ports.PORT}")
    for ref in refs:
        assert (ASSETS / ref.removeprefix("/")).exists(), ref
        resp = client.get(ref)
        assert resp.status_code == 200, ref
        ctype = resp.headers["content-type"]
        want = {".js": "javascript", ".css": "css", ".svg": "svg"}[Path(ref).suffix]
        assert want in ctype, (ref, ctype)
    # Все скрипты подключены, и подключены в порядке: ядро первым, запуск последним
    scripts = re.findall(r'<script defer src="/static/js/([^"?]+)', html)
    assert sorted(scripts) == sorted(p.relative_to(ASSETS / "static" / "js").as_posix() for p in JS_FILES)
    assert scripts[0] == "core.js" and scripts[-1] == "main.js"
