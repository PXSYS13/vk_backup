"""Страница программы в настоящем браузере (Playwright): каждая кнопка и каждый экран.

Сервер программы поднимается в этом же процессе на свободном порту — так подмена путей из
conftest.py (settings.json, «Загрузки», папка архива) доходит и до него. «Открыть папку»
не открывает проводник: вызов записывается, и тест проверяет, что именно открыли бы.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("playwright")

import uvicorn  # noqa: E402
from playwright.sync_api import Page, expect, sync_playwright  # noqa: E402

import webui  # noqa: E402
from vkbackup.backup import Backup  # noqa: E402
from vkbackup.store import DB_NAME, Store  # noqa: E402
from webapp import api, config, ports  # noqa: E402

ALL = ["messages", "friends", "photos", "videos", "wall", "music", "docs"]
ROUTES = ["home", "dashboard", "search", "stats", "setup", "security", "help", "support"]


def _browser_installed() -> bool:
    try:
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:  # noqa: BLE001 — нет драйвера или браузера: тесты пропускаются
        return False


pytestmark = pytest.mark.skipif(not _browser_installed(),
                                reason="нет браузера Playwright: uv run playwright install chromium")


# ── Сервер и состояние программы ──

@pytest.fixture(scope="session")
def live_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    old_port = ports.PORT
    ports.use_port(port)
    server = uvicorn.Server(uvicorn.Config(webui.app, host="127.0.0.1", port=port, log_level="warning",
                                           log_config=None))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started:
        assert time.time() < deadline, "сервер программы не запустился"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(10)
    ports.use_port(old_port)


@pytest.fixture(scope="session")
def base_url(live_server):
    return live_server


@pytest.fixture(autouse=True)
def app(monkeypatch, tmp_path):
    """Свой бэкап на каждый тест; «Открыть папку» и «Открыть архив» только записываются."""
    monkeypatch.setattr(api, "backup", Backup())
    api._stats_cache.clear()
    opened: list[Path] = []
    monkeypatch.setattr(api, "_open_local", opened.append)
    return SimpleNamespace(opened=opened, out=tmp_path / "out")


@pytest.fixture
def built(app, archive_zip):
    """Архив, собранный без сети: база, страницы, одна запись в истории запусков."""
    config.save(str(archive_zip), str(app.out), ALL, False)
    assert api.backup.start(archive_zip, app.out, ALL, False)
    api.backup.wait(30)
    assert api.backup.snapshot()["state"] == "done"
    return app.out


@pytest.fixture
def errors(page: Page):
    """Ошибки страницы: исключения в скриптах и всё, что браузер пишет как error."""
    found: list[str] = []
    page.on("console", lambda m: found.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: found.append(str(e)))
    return found


def _add_failed(out: Path, path: str = "photos/lost.jpg",
                error: str = "sun9-1.userapi.com ответил 404") -> None:
    store = Store(out / DB_NAME)
    try:
        store.add_media(path, "https://sun9-1.userapi.com/lost.jpg", "photos")
        store.media_failed(path, error, final=True)
    finally:
        store.close()


def _open(page: Page, route: str = "home") -> None:
    page.goto(f"/#/{route}")
    expect(page.locator(f"#screen-{route}")).to_be_visible()


def _toast(page: Page):
    return page.locator(".toast")


def _settled(page: Page, route: str) -> None:
    """Экран дорисован: заголовок на месте, данные, которые он догружает, пришли."""
    screen = page.locator(f"#screen-{route}")
    expect(screen.locator("h1").first).to_be_visible()
    for loading in ("Загружаю…", "Считаю…"):
        expect(screen).not_to_contain_text(loading)
    if route == "dashboard":
        expect(screen.locator(".kpi, .card.empty").first).to_be_visible()
    if route == "security":
        expect(screen.locator("details table tr").first).to_be_attached()


# ── Каркас: меню, тема, офлайн ──

@pytest.mark.parametrize("route", ROUTES)
def test_every_menu_item_opens_its_screen(page: Page, built, route):
    _open(page, "home" if route != "home" else "help")
    page.locator(f".nav a[data-route={route}]").click()
    expect(page).to_have_url(re.compile(rf"#/{route}$"))
    expect(page.locator(f"#screen-{route}")).to_be_visible()
    expect(page.locator(f"#screen-{route} h1").first).to_be_visible()
    for other in ROUTES:
        if other != route:
            expect(page.locator(f"#screen-{other}")).to_be_hidden()
    expect(page.locator(f".nav a[data-route={route}]")).to_have_class(re.compile(r"\bactive\b"))
    expect(page.locator(f".nav a[data-route={route}]")).to_have_attribute("aria-current", "page")


def test_brand_and_unknown_route_lead_home(page: Page, built):
    _open(page, "help")
    page.locator("a.brand").click()
    expect(page.locator("#screen-home")).to_be_visible()
    page.goto("/#/nope")
    expect(page.locator("#screen-home")).to_be_visible()


def test_theme_toggle_switches_and_is_remembered(page: Page):
    _open(page)
    html = page.locator("html")
    start = html.get_attribute("data-theme")
    other = "dark" if start != "dark" else "light"
    page.locator("#theme-toggle").click()
    expect(html).to_have_attribute("data-theme", other)
    expect(page.locator("#theme-label")).to_have_text("Светлая тема" if other == "dark" else "Тёмная тема")
    page.reload()
    expect(html).to_have_attribute("data-theme", other)
    page.locator("#theme-toggle").click()
    expect(html).to_have_attribute("data-theme", "light" if other == "dark" else "dark")


def test_offline_banner_when_program_is_closed(page: Page):
    _open(page)
    expect(page.locator("#offline")).to_be_hidden()
    page.route("**/api/status", lambda route: route.abort())
    expect(page.locator("#offline")).to_be_visible(timeout=8000)
    expect(page.locator("#offline")).to_contain_text("Программа не отвечает")
    page.unroute("**/api/status")
    expect(page.locator("#offline")).to_be_hidden(timeout=8000)


def test_side_lock_opens_security(page: Page):
    _open(page)
    expect(page.locator("#side-lock-text")).to_have_text("только файлы ВК")
    page.locator("#side-lock").click()
    expect(page.locator("#screen-security")).to_be_visible()


# ── Первый запуск и настройка ──

def test_onboarding_leads_to_setup(page: Page):
    _open(page)
    expect(page.locator("#screen-home h1")).to_have_text("Сохраните свой ВКонтакте на компьютер")
    order = page.get_by_role("link", name="Заказать архив у ВК")
    expect(order).to_have_attribute("target", "_blank")
    expect(order).to_have_attribute("href", re.compile(r"^https://vk\.com/data_protection"))
    page.get_by_role("link", name="Начать — 3 шага").click()
    expect(page.locator("#screen-setup")).to_be_visible()


def test_setup_finds_archive_and_saves(page: Page, archive_zip, app):
    _open(page, "setup")
    page.locator("[data-act=find]").click()
    expect(page.locator("#found")).to_have_text("Нашёл")
    expect(page.locator("#f-archive")).to_have_value(str(archive_zip))
    page.locator("#f-folder").fill(str(app.out))
    page.get_by_role("checkbox", name="Музыка").uncheck()
    page.locator("[data-act=save]").click()
    expect(_toast(page)).to_contain_text("Сохранено (архив страницы id1001)")
    saved = config.load()
    assert saved["archive"] == str(archive_zip) and saved["folder"] == str(app.out)
    assert "music" not in saved["sections"]
    # Шаг 2 отмечен выполненным, а сохранённое осталось в полях
    expect(page.locator("#screen-setup .step.done")).to_have_count(2)
    expect(page.locator("#f-archive")).to_have_value(str(archive_zip))


def test_setup_lets_choose_between_several_archives(page: Page, archive_zip):
    import fake_archive
    second = fake_archive.build(archive_zip.with_name("Archive (1).zip"))
    _open(page, "setup")
    page.locator("[data-act=find]").click()
    options = page.locator("[data-act=pick-archive]")
    expect(options).to_have_count(2)
    expect(page.locator("#found")).to_contain_text("Нашлось 2")
    options.filter(has_text="Archive.zip").click()
    expect(page.locator("#f-archive")).to_have_value(str(archive_zip))
    options.filter(has_text="Archive (1).zip").click()
    expect(page.locator("#f-archive")).to_have_value(str(second))
    expect(page.locator("[data-act=pick-archive][aria-pressed=true]")).to_have_count(1)


def test_setup_reports_nothing_found(page: Page):
    _open(page, "setup")
    page.locator("[data-act=find]").click()
    expect(page.locator("#found")).to_contain_text("архивов ВК не нашлось")


def test_setup_shows_errors_next_to_the_form(page: Page, archive_zip):
    _open(page, "setup")
    page.locator("#f-archive").fill("")
    page.locator("[data-act=save]").click()
    expect(page.locator("#setup-error")).to_contain_text("Укажите, где лежит архив")
    expect(page.locator(".toast.err")).to_be_visible()
    # Исправили — ошибка уходит
    page.locator("#f-archive").fill(str(archive_zip))
    page.locator("[data-act=save]").click()
    expect(page.locator("#setup-error")).to_be_hidden()


def test_setup_refuses_empty_section_list(page: Page, archive_zip):
    _open(page, "setup")
    page.locator("#f-archive").fill(str(archive_zip))
    for box in page.locator("input[name=sec]").all():
        box.uncheck()
    page.locator("[data-act=save]").click()
    expect(page.locator("#setup-error")).to_contain_text("Отметьте хотя бы один раздел")


def test_full_backup_from_setup_to_open_folder(page: Page, archive_zip, app):
    _open(page, "setup")
    page.locator("[data-act=find]").click()
    expect(page.locator("#f-archive")).to_have_value(str(archive_zip))
    page.locator("#f-folder").fill(str(app.out))
    page.locator("#f-download").uncheck()
    page.locator("[data-act=save-start]").click()
    expect(page).to_have_url(re.compile(r"#/home$"))
    expect(page.locator("#screen-home h1")).to_have_text("Всё сохранено", timeout=30000)
    expect(page.locator("#screen-home .hero-what")).to_contain_text("только текст, без сети")
    expect(page.locator("#screen-home .hero-what")).to_contain_text("Последний бэкап")

    page.locator("#screen-home [data-act=open-folder]").click()
    expect(_toast(page)).to_contain_text("Открываю папку")
    assert app.opened == [app.out]

    with page.context.expect_page() as tab:
        page.locator("#screen-home .hero a.btn.primary").click()
    archive_page = tab.value
    archive_page.wait_for_load_state()
    assert archive_page.url.endswith("/archive/index.html")
    expect(archive_page.locator("body")).to_contain_text("Иван Проверкин")

    page.locator("#screen-home [data-act=start]").click()
    expect(_toast(page)).to_contain_text("Бэкап запущен")
    api.backup.wait(30)
    assert api.backup.snapshot()["state"] == "done"
    expect(page.locator("#screen-home h1")).to_have_text("Всё сохранено", timeout=10000)


def test_start_without_settings_goes_to_setup(page: Page, archive_zip, app):
    config.save("", str(app.out), ALL, False)
    _open(page)
    page.get_by_role("link", name="Начать — 3 шага").click()
    expect(page.locator("#screen-setup")).to_be_visible()


# ── Главная с готовым архивом ──

def test_section_cards_open_archive_pages(page: Page, built):
    _open(page)
    cards = page.locator("#screen-home a.sec[target=_blank]")
    expect(cards.first).to_be_visible()
    hrefs = [c.get_attribute("href") for c in cards.all()]
    assert len(hrefs) >= 5
    for href in hrefs:
        assert page.request.get(href).status == 200, href
    expect(page.locator("#screen-home a.sec.promo")).to_have_css("display", "flex")
    page.locator("#screen-home a.sec.promo").click()
    expect(page.locator("#screen-stats")).to_be_visible()


def test_failed_files_can_be_retried_from_home(page: Page, built):
    _add_failed(built)
    _open(page)
    page.get_by_text("Какие файлы не скачались (1)").click()
    expect(page.locator("#screen-home table.t")).to_contain_text("photos/lost.jpg")
    page.locator("#screen-home [data-act=retry]").click()
    expect(_toast(page)).to_contain_text("Вернул в очередь: 1")
    expect(page.get_by_text("Какие файлы не скачались")).to_have_count(0)


def test_running_download_shows_progress_in_ring_and_tab_title(page: Page, built):
    real = page.request.get("/api/status").json()
    real["job"] = {**real["job"], "state": "running", "step": "download", "started_at": time.time() - 120,
                   "downloaded_now": 5, "bytes_now": 5_000_000}
    real["result"]["media"] = {"photos": {"pending": 5, "waiting": 0, "done": 5, "failed": 0, "bytes": 5_000_000}}
    page.route("**/api/status", lambda route: route.fulfill(json=real))
    _open(page)
    expect(page.locator("#screen-home .ring .pct")).to_contain_text("50")
    expect(page.locator("#screen-home .pill")).to_contain_text("Идёт скачивание")
    expect(page).to_have_title(re.compile(r"^50% · "))
    with page.expect_request(lambda r: r.url.endswith("/api/stop") and r.method == "POST"):
        page.locator("#screen-home [data-act=stop]").click()


def test_waiting_for_vk_buttons(page: Page, built):
    real = page.request.get("/api/status").json()
    real["job"] = {**real["job"], "state": "running", "step": "waiting", "next_retry": time.time() + 600,
                   "rounds": [{"time": time.time() - 60, "tried": 3, "got": 1}]}
    real["result"]["media"] = {"photos": {"pending": 0, "waiting": 3, "done": 7, "failed": 0, "bytes": 1}}
    page.route("**/api/status", lambda route: route.fulfill(json=real))
    _open(page)
    expect(page.locator("#screen-home .pill")).to_contain_text("Ждём ВК")
    expect(page.locator("#screen-home .banner").first).to_contain_text("сейчас не отвечают")
    with page.expect_request(lambda r: r.url.endswith("/api/retry-now") and r.method == "POST"):
        page.locator("#screen-home [data-act=retry-now]").click()
    expect(_toast(page)).to_be_visible()
    with page.expect_request(lambda r: r.url.endswith("/api/stop") and r.method == "POST"):
        page.locator("#screen-home .hero [data-act=stop]").click()


def test_error_state_offers_start_again(page: Page, built):
    real = page.request.get("/api/status").json()
    real["job"] = {**real["job"], "state": "error", "problem": "disk", "problem_text": "Нет места на диске"}
    page.route("**/api/status", lambda route: route.fulfill(json=real))
    _open(page)
    expect(page.locator("#screen-home .pill")).to_contain_text("Ошибка")
    expect(page.locator("#screen-home .card.err")).to_contain_text("Нет места на диске")
    expect(page.locator("#screen-home .hero [data-act=start]")).to_be_enabled()


def test_button_is_busy_while_its_request_runs(page: Page, built, monkeypatch):
    real_render = api.render_archive

    def slow_render(store, folder):
        time.sleep(1.5)
        return real_render(store, folder)

    monkeypatch.setattr(api, "render_archive", slow_render)
    calls: list[str] = []
    page.on("request", lambda r: calls.append(r.url) if r.url.endswith("/api/render") else None)
    _open(page, "dashboard")
    button = page.locator("#screen-dashboard [data-act=render]")
    button.click()
    expect(button).to_be_disabled()
    expect(button).to_have_attribute("aria-busy", "true")
    button.click(force=True)  # второй щелчок по занятой кнопке ничего не шлёт
    expect(_toast(page)).to_contain_text("Страницы архива обновлены", timeout=10000)
    expect(page.locator("#screen-dashboard [data-act=render]")).to_be_enabled()
    assert len(calls) == 1


def test_keyboard_focus_survives_a_button_request(page: Page, built):
    _open(page, "dashboard")
    _settled(page, "dashboard")
    button = page.locator("#screen-dashboard [data-act=render]")
    button.focus()
    page.keyboard.press("Enter")
    expect(_toast(page)).to_contain_text("Страницы архива обновлены")
    expect(page.locator("#screen-dashboard [data-act=render]")).to_be_focused()


def test_dashboard_does_not_redraw_on_every_poll_while_downloading(page: Page, built):
    real = page.request.get("/api/status").json()
    real["job"] = {**real["job"], "state": "running", "step": "download", "started_at": time.time() - 60}
    tick = {"n": 0}

    def status(route):
        tick["n"] += 1
        route.fulfill(json={**real, "job": {**real["job"], "downloaded_now": tick["n"], "bytes_now": tick["n"] * 1000}})

    page.route("**/api/status", status)
    _open(page, "dashboard")
    _settled(page, "dashboard")
    copy = page.locator("#dash-folder [data-act=copy]")
    copy.focus()
    page.wait_for_timeout(3500)  # два опроса статуса со свежими счётчиками
    assert tick["n"] >= 2
    expect(copy).to_be_focused()


def test_slash_works_on_russian_layout(page: Page, built):
    _open(page)
    # В русской раскладке клавиша «/» печатает точку: смотрим на саму клавишу
    page.evaluate("document.body.dispatchEvent(new KeyboardEvent('keydown', {key: '.', code: 'Slash', bubbles: true}))")
    expect(page.locator("#screen-search")).to_be_visible()


def test_server_error_is_not_reported_as_closed_program(page: Page, built):
    _open(page)
    expect(page.locator("#screen-home h1")).to_be_visible()
    page.route("**/api/status", lambda route: route.fulfill(status=500, json={"detail": "сбой"}))
    page.wait_for_timeout(3500)
    expect(page.locator("#offline")).to_be_hidden()


def test_dashboard_error_state(page: Page, built):
    page.route("**/api/dashboard", lambda route: route.fulfill(status=500, json={"detail": "база занята"}))
    _open(page, "dashboard")
    expect(page.locator("#screen-dashboard")).to_contain_text("Не получилось загрузить панель: база занята")
    page.unroute("**/api/dashboard")
    page.locator("#screen-dashboard [data-act=dash-refresh]").click()
    expect(page.locator("#screen-dashboard .kpi").first).to_be_visible()


def test_readiness_is_announced_in_words(page: Page, built):
    _open(page, "dashboard")
    _settled(page, "dashboard")
    expect(page.locator("[data-check=files] .sr-only")).to_have_text("Не выполнено:")
    expect(page.locator("[data-check=lock] .sr-only")).to_have_text("Выполнено:")


# ── Панель ──

def test_dashboard_without_archive_points_to_setup(page: Page):
    _open(page, "dashboard")
    expect(page.locator("#screen-dashboard")).to_contain_text("Архива ещё нет")
    page.locator("#screen-dashboard").get_by_role("link", name="Перейти к настройке").click()
    expect(page.locator("#screen-setup")).to_be_visible()


def test_dashboard_shows_everything_about_the_archive(page: Page, built, archive_zip):
    _open(page, "dashboard")
    dash = page.locator("#screen-dashboard")
    expect(dash.locator(".kpi").first).to_be_visible()
    expect(dash.locator(".kpi[data-k=messages] b")).to_have_text("8")
    expect(dash.locator(".kpi[data-k=friends] b")).to_have_text("2")
    # Готовность к удалению страницы: файлы не качались — пункт не выполнен
    expect(dash.locator("[data-check=pages]")).to_have_class(re.compile(r"\bok\b"))
    expect(dash.locator("[data-check=files]")).to_have_class(re.compile(r"\bbad\b"))
    expect(dash.locator("[data-check=lock]")).to_have_class(re.compile(r"\bok\b"))
    expect(dash.locator("#dash-score")).to_contain_text("из 5")
    expect(dash.locator("#dash-archive")).to_contain_text(str(archive_zip))
    expect(dash.locator("#dash-folder")).to_contain_text(str(built))
    expect(dash.locator("#dash-folder")).to_contain_text("свободно")
    expect(dash.locator("#dash-runs tbody tr")).to_have_count(1)
    expect(dash.locator("#dash-runs")).to_contain_text("Готово")
    expect(dash.locator("#dash-network")).to_contain_text("включён")


def test_dashboard_buttons(page: Page, built, app, base_url):
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base_url)
    _open(page, "dashboard")
    dash = page.locator("#screen-dashboard")
    expect(dash.locator(".kpi").first).to_be_visible()

    with page.expect_request("**/api/dashboard"):
        dash.locator("[data-act=dash-refresh]").click()

    dash.locator("[data-act=render]").click()
    expect(_toast(page)).to_contain_text("Страницы архива обновлены")

    dash.locator("[data-act=open-folder]").click()
    expect(_toast(page)).to_contain_text("Открываю папку")
    assert app.opened == [built]

    dash.locator("#dash-folder [data-act=copy]").click()
    expect(_toast(page)).to_contain_text("Скопировано")
    assert page.evaluate("navigator.clipboard.readText()") == str(built)

    with page.context.expect_page() as tab:
        dash.get_by_role("link", name="Открыть архив").click()
    assert tab.value.url.endswith("/archive/index.html")

    dash.locator("#dash-now [data-act=start]").click()
    expect(_toast(page)).to_contain_text("Бэкап запущен")
    api.backup.wait(30)
    expect(dash.locator("#dash-runs tbody tr")).to_have_count(2, timeout=10000)

    dash.get_by_role("link", name="Изменить").click()
    expect(page.locator("#screen-setup")).to_be_visible()


def test_dashboard_lists_failure_reasons_and_retries(page: Page, built):
    _add_failed(built, "photos/a.jpg")
    _add_failed(built, "photos/b.jpg", "psv4.userapi.com ответил 410")
    _add_failed(built, "photos/c.jpg", "замок: evil.example не в белом списке")
    _open(page, "dashboard")
    reasons = page.locator("#dash-reasons li")
    expect(reasons).to_have_count(2)
    expect(reasons.first).to_contain_text("2")
    expect(page.locator("#dash-files")).to_contain_text("Фото")
    page.locator("#screen-dashboard #dash-reasons [data-act=retry]").click()
    expect(_toast(page)).to_contain_text("Вернул в очередь: 3")
    expect(page.locator("#dash-reasons li")).to_have_count(0)


# ── Поиск ──

def test_search_finds_filters_and_opens_message(page: Page, built):
    _open(page, "search")
    q = page.locator("#q")
    expect(q).to_be_focused()
    q.fill("привет")
    hits = page.locator("#search-results .hit")
    expect(hits).to_have_count(2)
    expect(hits.first.locator("mark")).to_have_text(re.compile("привет", re.I))
    expect(page.locator("#q-peer option")).to_have_count(3)  # «во всех» + две беседы
    page.locator("#q-peer").select_option("2002")
    expect(hits).to_have_count(1)
    with page.context.expect_page() as tab:
        hits.first.click()
    assert re.search(r"#m100$", tab.value.url)
    page.locator("#q-peer").select_option("")
    expect(hits).to_have_count(2)
    q.press("Escape")
    expect(q).to_have_value("")
    expect(page.locator("#search-results .empty")).to_be_visible()


def test_search_shows_nothing_found(page: Page, built):
    _open(page, "search")
    page.locator("#q").fill("абракадабра")
    expect(page.locator("#search-results")).to_contain_text("Ничего не нашлось")


def test_search_more_button_asks_for_next_page(page: Page, built):
    def more(route):
        data = route.fetch().json()
        data["more"] = "limit=100" in route.request.url
        route.fulfill(json=data)

    page.route("**/api/search?*", more)
    _open(page, "search")
    page.locator("#q").fill("привет")
    button = page.locator("[data-act=search-more]")
    expect(button).to_be_visible()
    with page.expect_request(lambda r: "limit=200" in r.url):
        button.click()
    expect(button).to_have_count(0)


def test_slash_jumps_to_search(page: Page, built):
    _open(page)
    page.keyboard.press("/")
    expect(page.locator("#screen-search")).to_be_visible()
    expect(page.locator("#q")).to_be_focused()


def test_search_screen_before_backup(page: Page):
    _open(page, "search")
    expect(page.locator("#screen-search")).to_contain_text("когда архив будет сохранён")
    page.locator("#screen-search").get_by_role("link", name="На главную").click()
    expect(page.locator("#screen-home")).to_be_visible()


# ── ВК в цифрах, безопасность, помощь ──

def test_stats_screen_and_tooltips(page: Page, built):
    _open(page, "stats")
    stats = page.locator("#screen-stats")
    expect(stats.locator(".tile.hero-tile b")).to_have_text("8")
    stats.locator(".cols .col").first.hover()
    expect(page.locator("#tip")).to_be_visible()
    expect(page.locator("#tip")).not_to_have_text("")
    for link in stats.locator("a[target=_blank]").all():
        assert page.request.get(link.get_attribute("href")).status == 200


def test_security_screen(page: Page):
    _open(page, "security")
    sec = page.locator("#screen-security")
    expect(sec).to_contain_text("Сетевой замок включён")
    sec.get_by_text("Отпечатки файлов программы (SHA-256)").click()
    expect(sec.locator("details[open] table tr").first).to_be_visible()
    assert sec.locator("details[open] table tr").count() > 10


def test_help_answers_open_and_close(page: Page):
    _open(page, "help")
    items = page.locator("#screen-help details")
    assert items.count() >= 9
    for item in items.all():
        item.locator("summary").click()
        expect(item).to_have_attribute("open", "")
        item.locator("summary").click()
        expect(item).not_to_have_attribute("open", "")


# ── Поддержать проект ──

LINKS = {
    "donate": "https://www.donationalerts.com/r/davronsvv",
    "telegram": "https://t.me/davronsv",
    "youtube": "https://www.youtube.com/@davronsv",
    "github": "https://github.com/PXSYS13/vk_backup",
    "yadisk": "https://github.com/PXSYS13/yadisk_backup",
    "icloud": "https://github.com/PXSYS13/icloud_backup",
}


def test_support_screen_links(page: Page, built):
    _open(page, "support")
    for key, url in LINKS.items():
        link = page.locator(f"#screen-support a[data-link={key}]").first
        expect(link).to_be_visible()
        expect(link).to_have_attribute("href", url)
        expect(link).to_have_attribute("target", "_blank")
        expect(link).to_have_attribute("rel", re.compile(r"\bnoopener\b"))


DAY = 86400


def _flag_card(page: Page):
    return page.locator("#screen-home .flag-card")


def test_flag_opens_after_first_backup_and_calms_down(page: Page, built):
    _open(page)
    card = _flag_card(page)
    expect(card).to_be_visible()
    expect(card.locator("h2")).to_have_text("Будем на связи")
    expect(card.locator("a[data-link=telegram]")).to_have_text(re.compile("Подписаться"))
    expect(card.locator("a[data-link=donate]")).to_have_text(re.compile("Поддержать"))
    expect(card.locator("[data-promo=yadisk]")).to_be_visible()
    pennant = page.locator("#screen-home [data-act=flag-toggle]")
    expect(pennant).to_have_text(re.compile("От автора"))
    expect(pennant).to_have_attribute("aria-expanded", "true")
    # «Не сейчас» — карточка сворачивается, флажок остаётся; и так же после перезагрузки
    card.locator("[data-act=flag-later]").click()
    expect(card).to_have_count(0)
    expect(pennant).to_have_attribute("aria-expanded", "false")
    page.reload()
    expect(page.locator("#screen-home h1")).to_be_visible()
    expect(_flag_card(page)).to_have_count(0)
    # Флажок раскрывает карточку по щелчку
    page.locator("#screen-home [data-act=flag-toggle]").click()
    expect(_flag_card(page)).to_be_visible()


def test_flag_calms_after_a_link_click(page: Page, built):
    _open(page)
    with page.context.expect_page() as tab:
        _flag_card(page).locator("a[data-link=telegram]").click()
    assert tab.value.url.startswith("https://t.me/davronsv") or tab.value.url == "about:blank"
    tab.value.close()
    expect(_flag_card(page)).to_have_count(0)
    stored = page.evaluate("JSON.parse(localStorage.getItem('vkb.flag'))")
    assert stored["clickedAt"] > 0
    assert "telegram" not in str(stored)  # какую ссылку нажали — не записываем


def test_flag_calms_after_three_visits_without_a_click(page: Page, built):
    _open(page)
    for _ in range(2):
        expect(_flag_card(page)).to_be_visible()
        page.locator(".nav a[data-route=help]").click()
        page.locator(".nav a[data-route=home]").click()
    expect(_flag_card(page)).to_be_visible()  # третий визит
    page.locator(".nav a[data-route=help]").click()
    page.locator(".nav a[data-route=home]").click()
    expect(page.locator("#screen-home h1")).to_be_visible()
    expect(_flag_card(page)).to_have_count(0)
    expect(page.locator("#screen-home [data-act=flag-toggle]")).to_be_visible()


def test_flag_returns_after_a_month_with_a_new_backup(page: Page, built):
    _open(page)
    expect(_flag_card(page)).to_be_visible()
    stale = int((time.time() - 40 * DAY) * 1000)
    page.evaluate(f"""localStorage.setItem('vkb.flag', JSON.stringify(
        {{lastFullAt: {stale}, lastBackupId: 1, visits: 9, dismissed: {{home: 1}}}}))""")
    page.reload()
    expect(_flag_card(page)).to_be_visible()
    # Тот же бэкап через неделю — уже не показываем снова
    recent = int((time.time() - 7 * DAY) * 1000)
    page.evaluate(f"""localStorage.setItem('vkb.flag', JSON.stringify(
        {{lastFullAt: {recent}, lastBackupId: 1, visits: 9}}))""")
    page.reload()
    expect(page.locator("#screen-home h1")).to_be_visible()
    expect(_flag_card(page)).to_have_count(0)


def test_no_flag_while_backup_runs_or_fails(page: Page, built):
    real = page.request.get("/api/status").json()

    def status_with(job):  # обработчику Playwright передаёт и запрос вторым аргументом — job в замыкании
        return lambda route: route.fulfill(json={**real, "job": {**real["job"], **job}})

    for job in ({"state": "running", "step": "download"}, {"state": "error", "problem": "disk", "problem_text": "Нет места"}):
        page.route("**/api/status", status_with(job))
        _open(page)
        expect(page.locator("#screen-home .pill")).to_be_visible()
        expect(page.locator("#screen-home [data-act=flag-toggle]")).to_have_count(0)
        expect(_flag_card(page)).to_have_count(0)
        page.locator(".nav a[data-route=stats]").click()
        expect(page.locator("#screen-stats .tile").first).to_be_visible()
        expect(page.locator("#screen-stats .thanks-card")).to_have_count(0)
        page.unroute("**/api/status")


def test_hide_flag_switch_and_own_programs(page: Page, built):
    _open(page, "support")
    sup = page.locator("#screen-support")
    expect(sup).to_contain_text("Программа никуда не сообщает, нажали ли вы на ссылку")
    sup.locator("[data-act=promo-own][data-app=yadisk]").click()
    expect(sup.locator("[data-promo=yadisk]")).to_have_count(0)
    expect(sup.locator("[data-promo=icloud]")).to_be_visible()
    hide = sup.locator("[data-act=flag-hide]")
    expect(hide).to_have_attribute("aria-pressed", "false")
    hide.click()
    expect(hide).to_have_attribute("aria-pressed", "true")
    page.locator(".nav a[data-route=home]").click()
    expect(page.locator("#screen-home h1")).to_be_visible()
    expect(page.locator("#screen-home [data-act=flag-toggle]")).to_have_count(0)
    expect(_flag_card(page)).to_have_count(0)
    expect(page.locator(".nav a[data-route=support]")).to_be_visible()  # пункт меню остаётся всегда


def test_clicks_outside_the_flag_cards_do_not_touch_the_flag(page: Page, built):
    _open(page, "help")
    with page.context.expect_page() as tab:
        page.locator("#screen-help .ask-card a[data-link=telegram]").click()
    tab.value.close()
    assert page.evaluate("JSON.parse(localStorage.getItem('vkb.flag') || '{}').clickedAt") is None
    page.locator(".nav a[data-route=home]").click()
    expect(_flag_card(page)).to_be_visible()


def test_flag_works_when_the_browser_blocks_storage(page: Page, built):
    page.add_init_script("""Object.defineProperty(window, 'localStorage', {get() { throw new Error('blocked'); }});""")
    _open(page)
    card = _flag_card(page)
    expect(card).to_be_visible()
    card.locator("[data-act=flag-later]").click()
    expect(_flag_card(page)).to_have_count(0)


def test_full_score_card_follows_the_flag_pause(page: Page, built):
    """Новый бэкап — новый номер, но карточка «5 из 5» не возвращается раньше флажка."""
    def all_ok(route):
        data = route.fetch().json()
        data["checks"] = [{**c, "ok": True} for c in data["checks"]]
        route.fulfill(json=data)

    page.route("**/api/dashboard", all_ok)
    recent = int((time.time() - 3 * DAY) * 1000)
    page.add_init_script(f"""localStorage.setItem('vkb.flag', JSON.stringify(
        {{lastFullAt: {recent}, lastBackupId: 1, visits: 9, clickedAt: {recent}}}))""")
    _open(page, "dashboard")
    expect(page.locator("#screen-dashboard .kpi").first).to_be_visible()
    expect(page.locator("#screen-dashboard .five-card")).to_have_count(0)


def test_dashboard_full_score_card(page: Page, built):
    def all_ok(route):
        data = route.fetch().json()
        data["checks"] = [{**c, "ok": True} for c in data["checks"]]
        route.fulfill(json=data)

    page.route("**/api/dashboard", all_ok)
    _open(page, "dashboard")
    card = page.locator("#screen-dashboard .five-card")
    expect(card).to_be_visible()
    expect(card.locator("h2")).to_have_text("5 из 5: копия полная")
    expect(card.locator("a[data-link=telegram]")).to_be_visible()
    expect(card.locator("[data-promo=icloud]")).to_be_visible()
    card.locator("[data-act=flag-later]").click()
    expect(page.locator("#screen-dashboard .five-card")).to_have_count(0)


def test_stats_thanks_card_and_copy_summary(page: Page, built, base_url):
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base_url)
    _open(page, "stats")
    card = page.locator("#screen-stats .thanks-card")
    expect(card.locator("h2")).to_have_text("8 сообщений за 3 года — теперь у вас")
    expect(card.locator("a[data-link=donate]")).to_be_visible()
    card.locator("[data-act=copy]").click()
    expect(_toast(page)).to_contain_text("Скопировано")
    text = page.evaluate("navigator.clipboard.readText()")
    assert "8 сообщений за 3 года" in text and "github.com/PXSYS13/vk_backup" in text


def test_help_points_to_channel_and_questions(page: Page):
    _open(page, "help")
    card = page.locator("#screen-help .ask-card")
    expect(card.locator("h2")).to_have_text("Не нашли ответ?")
    expect(card.locator("a[data-link=telegram]")).to_have_text(re.compile("В канал"))
    expect(card.locator("a[data-link=issues]")).to_have_attribute(
        "href", "https://github.com/PXSYS13/vk_backup/issues/new")
    expect(card.locator("a[data-link=donate]")).to_have_count(0)  # человек застрял — денег не просим


def test_page_requests_nothing_outside_the_program(page: Page, built, base_url):
    """Ссылки на канал, донат и соседние программы человек открывает сам — страница по ним
    ничего не запрашивает: ни картинок, ни счётчиков, ни аналитики."""
    outside: list[str] = []
    page.on("request", lambda r: outside.append(r.url) if not r.url.startswith(base_url) else None)
    for route in ROUTES:
        _open(page, route)
        _settled(page, route)
    assert outside == []


# ── Сквозные проверки ──

def test_no_script_errors_on_any_screen(page: Page, built, errors):
    for route in ROUTES:
        _open(page, route)
        _settled(page, route)
    assert errors == []


@pytest.mark.parametrize("route", ROUTES)
def test_phone_width_has_no_sideways_scroll(page: Page, built, route):
    page.set_viewport_size({"width": 375, "height": 800})
    _open(page, route)
    _settled(page, route)
    wide = page.evaluate("""() => document.documentElement.scrollWidth <= window.innerWidth + 1 ? [] :
      [...document.querySelectorAll('body *')].filter((e) => e.getBoundingClientRect().right > window.innerWidth + 1)
        .slice(0, 5).map((e) => `${e.tagName}.${e.className} → ${Math.round(e.getBoundingClientRect().right)}px`)""")
    assert wide == []


@pytest.mark.parametrize("route", ROUTES)
def test_every_control_has_a_name(page: Page, built, route):
    _open(page, route)
    _settled(page, route)
    nameless = page.evaluate("""(route) => [...document.querySelectorAll(
        `#screen-${route} button, #screen-${route} a, #screen-${route} input, #screen-${route} select`)]
      .filter((el) => el.offsetParent !== null)
      .filter((el) => !(el.getAttribute('aria-label') || el.textContent.trim() || el.closest('label')))
      .map((el) => el.outerHTML.slice(0, 120))""", route)
    assert nameless == []
