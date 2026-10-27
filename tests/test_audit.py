"""Аудит кода: проверки, что программа устроена так, как обещает SECURITY.md.

Это не тесты поведения, а «сторож» на будущее: если кто-то (в том числе автор) добавит
сетевой код в новом месте, выполнение строк, запуск программ или новую зависимость,
тест упадёт и потребует осознанно поправить и этот список, и SECURITY.md.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE = sorted([*(ROOT / "vkbackup").rglob("*.py"), *(ROOT / "webapp").rglob("*.py"), ROOT / "webui.py"])

NETWORK_MODULES = {"socket", "ssl", "http.client", "http.server", "urllib.request", "urllib3", "requests",
                   "httpx", "aiohttp", "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc",
                   "websocket", "websockets", "asyncio", "selectors"}
# Где сетевой код разрешён — и зачем
NETWORK_ALLOWED = {
    "vkbackup/firewall.py": {"socket"},           # сетевой замок: проверяет и открывает соединения
    "vkbackup/net.py": {"http.client", "ssl"},    # скачивание файла по ссылке из архива
    "webapp/ports.py": {"socket", "http.client"},  # выбор свободного порта на 127.0.0.1
}
# Выполнение строк как кода, запуск программ, низкоуровневый доступ — где разрешено и зачем
RISKY_ALLOWED = {
    ("vkbackup/files.py", "ctypes"),       # Windows: не дать компьютеру уснуть во время бэкапа
    ("webapp/api.py", "os.startfile"),     # открыть папку архива в проводнике по кнопке
}
RISKY_NAMES = {"eval", "exec", "compile", "__import__"}
RISKY_MODULES = {"subprocess", "ctypes", "pickle", "marshal", "shelve", "multiprocessing", "pty", "code"}
RISKY_ATTRS = {"os.system", "os.popen", "os.startfile", "os.exec", "os.spawn"}


def _rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def _imports(tree: ast.AST) -> set[str]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found |= {f"{node.module}.{a.name}" for a in node.names}
    return found


def test_network_code_lives_only_in_known_places():
    for path in CODE:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        net = {m for m in _imports(tree) if m in NETWORK_MODULES or m.split(".")[0] in NETWORK_MODULES - {"http"}}
        allowed = NETWORK_ALLOWED.get(_rel(path), set())
        assert net <= allowed, f"{_rel(path)}: сетевой код {sorted(net - allowed)} — допишите его в SECURITY.md и сюда"


def test_no_code_execution_or_process_launch():
    for path in CODE:
        rel = _rel(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in RISKY_NAMES, f"{rel}: {node.func.id}()"
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                name = f"{node.value.id}.{node.attr}"
                if any(name.startswith(r) for r in RISKY_ATTRS):
                    assert (rel, name) in RISKY_ALLOWED, f"{rel}: {name}"
        for module in _imports(tree):
            top = module.split(".")[0]
            if top in RISKY_MODULES:
                assert (rel, top) in RISKY_ALLOWED, f"{rel}: import {module}"


def test_local_server_listens_only_on_this_computer():
    from webapp import ports
    assert ports.HOST == "127.0.0.1"
    assert 'host=ports.HOST' in (ROOT / "webui.py").read_text(encoding="utf-8")


def test_lock_is_installed_before_anything_else():
    source = (ROOT / "webui.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    body = [n for n in tree.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    # Первые инструкции: from __future__, from pathlib, from vkbackup import firewall, firewall.install(...)
    first_call = next(n for n in body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call))
    assert ast.unparse(first_call).startswith("firewall.install(")
    before = body[: body.index(first_call)]
    assert all(isinstance(n, (ast.ImportFrom, ast.Import)) for n in before)
    assert {ast.unparse(n) for n in before} <= {"from __future__ import annotations",
                                                "from pathlib import Path", "from vkbackup import firewall"}


def test_only_two_runtime_dependencies():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"^dependencies = \[(.*?)^\]", text, re.S | re.M).group(1)
    names = sorted(re.split(r"[<>=!~ ;\[]", d, maxsplit=1)[0] for d in re.findall(r'^\s*"([^"]+)"', block, re.M))
    assert names == ["fastapi", "uvicorn"]


def test_program_page_loads_nothing_from_internet():
    html = (ROOT / "webui_assets" / "app.html").read_text(encoding="utf-8")
    assert not re.search(r'(?:src|href)="https?://', html)
    js = (ROOT / "webui_assets" / "static" / "app.js").read_text(encoding="utf-8")
    assert all(not a.startswith(("'http", '"http', "`http")) for a in re.findall(r"fetch\(\s*([^,)]+)", js))
    # Единственный внешний адрес — ссылка на страницу ВК «Защита данных», которую человек открывает сам
    urls = set(re.findall(r"https?://[^\s'\"`)<]+", js))
    assert urls == {"https://vk.com/data_protection?section=rules&scroll_to_archive=1"}
    css = (ROOT / "webui_assets" / "static" / "app.css").read_text(encoding="utf-8")
    assert "http" not in css and "@import" not in css


def test_archive_style_has_no_outside_resources():
    css = (ROOT / "vkbackup" / "render" / "style.css").read_text(encoding="utf-8")
    assert "http" not in css and "@import" not in css and "url(" not in css
