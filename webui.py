"""Бэкап ВКонтакте — страница программы на этом компьютере.

Запуск:
  uv run webui.py
  → http://127.0.0.1:8020 (если порт занят чужой программой — следующий свободный)

Первым делом ставится сетевой замок (vkbackup/firewall.py): до того, как загрузится
любой другой код, программе уже нельзя соединиться ни с кем, кроме файловых серверов ВК
(с них скачиваются фото и голосовые по ссылкам из архива) и самого компьютера.
Журнал всех соединений — logs/network.log.
"""

from __future__ import annotations

# ── Сетевой замок: самым первым, до остальных импортов ──
from pathlib import Path

from vkbackup import firewall

firewall.install(Path(__file__).resolve().parent / "logs")

import logging  # noqa: E402
import mimetypes  # noqa: E402
import os  # noqa: E402
import platform  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
from logging.handlers import RotatingFileHandler  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from vkbackup import APP_NAME, APP_VERSION  # noqa: E402
from webapp import api, paths, ports  # noqa: E402

log = logging.getLogger("webui")

# Без /docs и /openapi.json: страница программы — только та, что в webui_assets
app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, openapi_url=None)
app.middleware("http")(ports.csrf_guard)
app.include_router(api.router)

# Windows берёт MIME из реестра, и там .js бывает text/plain — браузер такой скрипт не выполнит
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
app.mount("/static", StaticFiles(directory=str(paths.TEMPLATES_DIR / "static")), name="static")


@app.middleware("http")
async def _no_outside_resources(request, call_next):
    """Страница программы тоже ничего не грузит из интернета: это видно и в браузере."""
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'none'")
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


def _setup_logging() -> None:
    """Журнал программы: действия, ошибки — без ключа доступа и без текста переписок."""
    paths.LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    handler = RotatingFileHandler(paths.WEBUI_LOG, maxBytes=5 * 1024 * 1024, backupCount=3,
                                  encoding="utf-8")
    handler.setFormatter(fmt)
    for name in ("webui", "vkbackup", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        lg.addHandler(handler)
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(fmt)
    logging.getLogger("uvicorn.error").addHandler(console)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    _setup_logging()
    log.info("%s v%s старт: python %s, %s", APP_NAME, APP_VERSION, platform.python_version(),
             platform.platform())

    import uvicorn

    wanted = ports.PORT
    sock, port, running = ports.choose_port(wanted, 1 if ports.PORT_FIXED else ports.PORT_TRIES)
    if running is not None:
        ports.show_running_copy(port, running)
        return
    if sock is None:
        print(f"  Порты {wanted}–{wanted + ports.PORT_TRIES - 1} заняты. Закройте лишние программы и запустите снова.")
        sys.exit(1)
    ports.use_port(port)
    url = f"http://{ports.HOST}:{port}"
    print("=" * 65)
    print(f"  {APP_NAME} · v{APP_VERSION}")
    print(f"  Адрес: {url}")
    print("  Сетевой замок включён: программа соединяется только с файловыми серверами ВК.")
    print(f"  Журнал соединений: {paths.LOG_DIR / 'network.log'}")
    print("=" * 65)
    print()
    print("  Браузер откроется сам. Чтобы остановить — закройте это окно или нажмите Ctrl+C.")
    print()
    if os.getenv("VKBACKUP_NO_BROWSER") != "1":
        threading.Thread(target=ports.open_browser_when_ready, args=(ports.HOST, port), daemon=True).start()
    server = uvicorn.Server(uvicorn.Config(app, host=ports.HOST, port=port, log_level="warning",
                                           log_config=None))
    try:
        server.run(sockets=[sock])
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
