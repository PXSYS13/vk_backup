"""Единственный HTTP-клиент программы — на стандартной библиотеке Python, без сторонних.

Программа делает в интернете ровно одно: скачивает файл по прямой ссылке из архива ВК
(download). Других запросов нет, и всё, что уходит на сервер, видно в этом файле:
- только GET, только HTTPS с проверкой сертификата: http:// превращается в https://;
- соединение открывает сетевой замок (firewall.connect): имя не из белого списка
  не ищется и не соединяется, даже если на него ведёт перенаправление;
- заголовки — только User-Agent и Accept-Encoding: ни cookies, ни данных аккаунта, ни
  содержимого архива на сервер не уходит. Прокси из настроек системы не используются;
- в тексте ошибок — только имя сервера, без пути и параметров ссылки.
"""

from __future__ import annotations

import http.client
import os
import ssl
import threading
import urllib.parse
from pathlib import Path

from vkbackup import firewall

TIMEOUT = 60
MAX_REDIRECTS = 5
USER_AGENT = "VKBackup/0.1"
_CHUNK = 256 * 1024

_SSL = ssl.create_default_context()
_tls = threading.local()


class NetError(OSError):
    """Сеть или сервер не ответили как надо. Текст — без пути и параметров адреса."""

    def __init__(self, message: str, status: int | None = None, host: str = ""):
        super().__init__(message)
        self.status = status
        self.host = host


class _Connection(http.client.HTTPSConnection):
    """HTTPS-соединение, адрес для которого выдаёт только сетевой замок."""

    def connect(self) -> None:
        sock = firewall.connect(self.host, self.port, self.timeout)
        self.sock = _SSL.wrap_socket(sock, server_hostname=self.host)


def split_url(url: str) -> tuple[str, int, str]:
    """(имя, порт, путь с параметрами). http:// → https://, порт — только 443; иначе — отказ."""
    parts = urllib.parse.urlsplit(url.strip())
    if parts.scheme not in ("https", "http"):
        raise NetError("адрес не https")
    host = (parts.hostname or "").lower()
    if not host:
        raise NetError("в адресе нет сервера")
    if parts.port not in (None, 443):
        raise NetError(f"{host}: нестандартный порт")
    port = 443
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return host, port, path


def _conn(host: str, port: int) -> _Connection:
    pool = getattr(_tls, "pool", None)
    if pool is None:
        pool = _tls.pool = {}
    conn = pool.get((host, port))
    if conn is None:
        conn = pool[(host, port)] = _Connection(host, port, timeout=TIMEOUT)
    return conn


def _drop(host: str, port: int) -> None:
    conn = getattr(_tls, "pool", {}).pop((host, port), None)
    if conn is not None:
        conn.close()


def close_all() -> None:
    """Закрыть соединения этого потока (в конце работы потока)."""
    for key in list(getattr(_tls, "pool", {})):
        _drop(*key)


def _get(url: str):
    """GET с переходами по перенаправлениям. Возвращает (ответ, имя сервера, порт)."""
    hdrs = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    for _ in range(MAX_REDIRECTS + 1):
        host, port, path = split_url(url)
        for attempt in (1, 2):
            conn = _conn(host, port)
            try:
                conn.request("GET", path, headers=hdrs)
                resp = conn.getresponse()
                break
            except firewall.BlockedConnection:
                _drop(host, port)
                raise
            except (OSError, http.client.HTTPException) as e:
                _drop(host, port)
                # Сервер закрыл соединение, которое мы держали открытым: пробуем один раз заново
                if attempt == 2:
                    raise NetError(f"нет связи с {host}: {type(e).__name__}", host=host) from None
        if resp.status in (301, 302, 303, 307, 308):
            location = resp.getheader("Location") or ""
            resp.read()
            if not location:
                raise NetError(f"{host}: перенаправление без адреса", resp.status, host)
            url = urllib.parse.urljoin(f"https://{host}{path}", location)
            continue
        return resp, host, port
    raise NetError("слишком много перенаправлений")


def download(url: str, dest: Path) -> int:
    """Файл по адресу — в dest. Пишет во временный dest.part и переименовывает: обрыв не оставит
    половину файла под настоящим именем. Возвращает размер в байтах."""
    resp, host, port = _get(url)
    if resp.status != 200:
        resp.read()
        if resp.will_close:
            _drop(host, port)
        raise NetError(f"{host} ответил {resp.status}", resp.status, host)
    part = dest.with_name(dest.name + ".part")
    size = 0
    try:
        # Ошибки записи (нет места, нет доступа к папке) — это OSError с диска, не NetError:
        # их видно отдельно и с ними не помогут повторы
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(part, "wb") as f:
            while True:
                try:
                    chunk = resp.read(_CHUNK)
                except (OSError, http.client.HTTPException) as e:
                    raise NetError(f"{host}: обрыв при скачивании ({type(e).__name__})",
                                   host=host) from None
                if not chunk:
                    break
                f.write(chunk)
                size += len(chunk)
        expected = resp.getheader("Content-Length")
        if expected and expected.isdigit() and int(expected) != size:
            raise NetError(f"{host} прислал файл не целиком", host=host)
        os.replace(part, dest)
    except BaseException:
        _drop(host, port)
        try:
            part.unlink()
        except OSError:
            pass
        raise
    if resp.will_close:
        _drop(host, port)
    return size
