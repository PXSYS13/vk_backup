# Для разработчиков

## Окружение

Проект живёт на [uv](https://docs.astral.sh/uv/): он сам ставит нужный Python (3.10+) и зависимости из `uv.lock`.

```bash
uv sync              # окружение с зависимостями для разработки (pytest, ruff, httpx)
uv run webui.py      # страница-пульт на http://127.0.0.1:8020
uv run pytest -q     # тесты
uv run ruff check .  # линтер
```

Переменные окружения: `VKBACKUP_NO_BROWSER=1` — не открывать браузер при запуске; `VKBACKUP_PORT=8030` — другой порт.

## Как устроен проект

```
webui.py              запуск: сетевой замок — первой строкой, потом приложение FastAPI
webapp/               сервер страницы-пульта
  api.py              /api/…: статус, настройки, запуск, «Безопасность»
  ports.py            выбор порта на 127.0.0.1, защита от чужих сайтов (CSRF, DNS-rebinding)
  config.py, paths.py настройки (settings.json) и пути программы
webui_assets/         страница-пульт: app.html, static/app.css, static/app.js (без сборки и библиотек)

vkbackup/
  firewall.py         сетевой замок (аудит-хуки Python): только *.userapi.com, *.vkuserphoto.ru, *.okcdn.ru
  net.py              единственный сетевой код: download(url, dest)
  archive.py          чтение архива ВК (ZIP или папка, cp1251 или UTF-8)
  parse.py            разбор страниц архива ВК по классам их разметки
  importer.py         архив → база, файлы — в очередь
  store.py            SQLite: objects, messages, progress, media
  media.py            скачивание очереди в несколько потоков
  backup.py           весь бэкап по шагам и его состояние для интерфейса
  render/             HTML-страницы архива и их стили (без скриптов, с CSP)

tests/
  fake_archive.py     поддельный архив ВК с той же разметкой, что у настоящего
  test_audit.py       тест-сторож: где сетевой код, нет ли eval/subprocess, сколько зависимостей
  test_firewall.py    замок в отдельном процессе
```

## Правила

- Тексты интерфейса, журналы, комментарии и документация — на русском, простыми словами.
- **Любой новый сетевой код** — только в `vkbackup/net.py` и только через `firewall.connect`. Новый домен в `firewall.ALLOWED_DOMAINS` — только файловый сервер ВК, на который ведут ссылки из архива, с объяснением в комментарии и в `SECURITY.md`. `tests/test_audit.py` упадёт, если сетевой код, `eval`/`exec`, `subprocess` или новая зависимость появятся без этого.
- Разметку архива ВК в тестах воспроизводит `tests/fake_archive.py`. Настоящие архивы (свои или чужие) в репозиторий не кладём: в них личные данные.
- Тесты, которые пишут кириллицу в файлы, передают `encoding="utf-8"`: у GitHub Actions на Windows кодировка по умолчанию cp1252. CI запускает тесты с `PYTHONWARNDEFAULTENCODING=1`.
- `.bat`-файлы хранятся с окончаниями строк CRLF, иначе cmd.exe путает метки.
- Версия uv закреплена в `webui.bat`, `webui.sh` и `.github/workflows/ci.yml` вместе с SHA-256 её архивов. Обновляя версию, поменяйте суммы и пересоберите `uv.lock` той же версией: `uvx --from uv==<версия> uv lock`.
