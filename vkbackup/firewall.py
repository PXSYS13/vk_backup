"""Сетевой замок: программа соединяется только с файловыми серверами ВКонтакте и с самим компьютером.

Как это устроено. Python сообщает о каждом сетевом действии — поиске адреса по имени,
соединении, отправке пакета — через аудит-хуки (PEP 578). Замок ставится первым делом
при запуске программы, и снять его нельзя: так устроен Python. Замок пропускает:

- имена из белого списка ALLOWED_DOMAINS — серверы, на которых ВК хранит фото, голосовые
  и документы. Ни сайта vk.com, ни API ВК, ни входа в аккаунт в списке нет: программе
  они не нужны, она читает архив, который вы сами скачали у ВК;
- адреса самого компьютера (127.0.0.1, ::1, localhost) — на них работает страница программы;
- соединения с адресом, который программа сама только что получила для имени из списка.

Всё остальное — исключение BlockedConnection: имя не ищется, соединение не открывается,
а попытка пишется в журнал logs/network.log. Каждое новое разрешённое имя тоже пишется
в журнал — по нему видно всё, с кем программа говорила.

Замок — защита «на всякий случай», а не песочница: он стоит внутри той же программы,
которую проверяет. Независимая проверка снаружи (монитор ресурсов Windows, TCPView,
брандмауэр) описана в SECURITY.md.
"""

from __future__ import annotations

import ipaddress
import socket
import sys
import threading
import time
from collections import Counter
from pathlib import Path

# Файловые серверы ВКонтакте — те, на которые ведут ссылки внутри архива данных.
# Имя пропускается, если оно совпадает с доменом или кончается на «.домен».
# vk.com и vk.ru здесь нет намеренно: на этих адресах — вход в аккаунт и API.
ALLOWED_DOMAINS = (
    "userapi.com",     # фото (sun9-….userapi.com), голосовые и документы (psv4.userapi.com)
    "vkuserphoto.ru",  # фото на новых серверах ВК
    "okcdn.ru",        # обложки видео (iv.okcdn.ru)
)

_LOCAL_NAMES = {"localhost", "localhost.localdomain"}


class BlockedConnection(PermissionError):
    """Программа попыталась соединиться не с файловым сервером ВК — замок не пустил."""


_lock = threading.Lock()
_installed = False
_log_file: Path | None = None
# Адреса, которые замок сам получил для разрешённых имён: только с ними можно соединиться
_resolved_ips: set[str] = set()
# Для экрана «Безопасность»: сколько раз программа обращалась к каждому имени за этот запуск
allowed_counts: Counter[str] = Counter()
blocked: list[dict] = []
_seen_hosts: set[str] = set()


def host_allowed(host: str) -> bool:
    """Имя из белого списка: сам домен или его поддомен (не «evilvk.com», не «vk.com.evil.ru»)."""
    host = host.strip().lower().rstrip(".")
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)


def _ip(value: object) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if isinstance(value, bytes):
        value = value.decode("ascii", "replace")
    if not isinstance(value, str):
        return None
    try:
        return ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return None


def _is_local(value: object) -> bool:
    if isinstance(value, bytes):
        value = value.decode("ascii", "replace")
    if isinstance(value, str) and value.strip().lower().rstrip(".") in _LOCAL_NAMES:
        return True
    ip = _ip(value)
    return ip is not None and ip.is_loopback


def _journal(kind: str, text: str) -> None:
    if _log_file is None:
        return
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {kind} | {text}\n"
    try:
        with open(_log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def _block(what: str, target: object) -> None:
    text = f"{what}: {target!r}"
    with _lock:
        blocked.append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "what": what, "target": repr(target)})
        del blocked[:-100]
    _journal("ЗАБЛОКИРОВАНО", text)
    raise BlockedConnection(f"Сетевой замок не пустил программу: {text}")


def _check_name(host: object) -> None:
    """Поиск адреса по имени (DNS): разрешённое имя, адрес компьютера или уже полученный нами адрес."""
    if host is None or _is_local(host):
        return
    ip = _ip(host)
    if ip is not None:
        with _lock:
            known = str(ip) in _resolved_ips
        if not known:
            _block("адрес не файлового сервера ВК", host)
        return
    name = host.decode("idna", "replace") if isinstance(host, bytes) else str(host)
    if not host_allowed(name):
        _block("имя не из белого списка", name)


def _check_address(address: object) -> None:
    """Соединение или отправка пакета: только на компьютер или на адрес, полученный для имени из списка."""
    if not isinstance(address, tuple) or not address:
        return  # AF_UNIX и прочие локальные сокеты — не сеть
    target = address[0]
    if _is_local(target):
        return
    ip = _ip(target)
    with _lock:
        known = ip is not None and str(ip) in _resolved_ips
    if not known:
        _block("соединение не с файловым сервером ВК", target)


def _hook(event: str, args: tuple) -> None:
    if not event.startswith("socket."):
        return
    if event == "socket.getaddrinfo":
        _check_name(args[0])
    elif event in ("socket.gethostbyname", "socket.gethostbyname_ex"):
        _check_name(args[0])
    elif event in ("socket.connect", "socket.sendto", "socket.sendmsg"):
        if len(args) >= 2:
            _check_address(args[1])


def resolve(host: str, port: int) -> list[tuple]:
    """Адреса разрешённого имени. Только через эту функцию программа узнаёт, куда соединяться."""
    host = host.strip().lower().rstrip(".")
    if not host_allowed(host):
        _block("имя не из белого списка", host)
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    with _lock:
        for info in infos:
            ip = _ip(info[4][0])
            if ip is not None:
                _resolved_ips.add(str(ip))
        allowed_counts[host] += 1
        new = host not in _seen_hosts
        _seen_hosts.add(host)
    if new:
        _journal("разрешено", host)
    return infos


def connect(host: str, port: int, timeout: float) -> socket.socket:
    """TCP-соединение с разрешённым именем: адрес берём только из resolve()."""
    last: OSError | None = None
    for family, type_, proto, _canon, sockaddr in resolve(host, port):
        sock = socket.socket(family, type_, proto)
        try:
            sock.settimeout(timeout)
            sock.connect(sockaddr)
            return sock
        except OSError as e:
            sock.close()
            if isinstance(e, BlockedConnection):
                raise
            last = e
    raise last or OSError(f"Не удалось соединиться с {host}")


def install(log_dir: Path | None = None) -> None:
    """Ставит замок на весь процесс. Повторный вызов только меняет папку журнала."""
    global _installed, _log_file
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        _log_file = log_dir / "network.log"
    if _installed:
        return
    sys.addaudithook(_hook)
    _installed = True
    _journal("замок включён", "разрешены: " + ", ".join(ALLOWED_DOMAINS) + " и сам компьютер")


def installed() -> bool:
    return _installed


def snapshot() -> dict:
    """Для экрана «Безопасность»: с кем говорила программа и что замок не пустил."""
    with _lock:
        return {
            "installed": _installed,
            "allowed_domains": list(ALLOWED_DOMAINS),
            "hosts": sorted(allowed_counts.items(), key=lambda kv: (-kv[1], kv[0])),
            "blocked": list(blocked),
            "log_file": str(_log_file) if _log_file else None,
        }
