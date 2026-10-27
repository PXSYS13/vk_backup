"""Сетевой замок. Замок ставится на процесс навсегда, поэтому проверки — в отдельном процессе.

Запросы, которые замок обрывает, обрываются до поиска адреса: тестам интернет не нужен.
"""

import json
import subprocess
import sys
import textwrap

from vkbackup import firewall

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent


def test_host_allowed_only_vk_storage():
    assert firewall.host_allowed("sun9-57.userapi.com")
    assert firewall.host_allowed("psv4.userapi.com")
    assert firewall.host_allowed("iv.okcdn.ru")
    assert firewall.host_allowed("USERAPI.COM.")
    for host in ("vk.com", "api.vk.com", "oauth.vk.com", "vk.ru", "login.vk.ru",  # сайт и API — нет
                 "evil-userapi.com", "userapi.com.evil.ru", "example.org", "", "github.com"):
        assert not firewall.host_allowed(host), host


def test_no_vk_site_or_api_in_allowlist():
    for domain in firewall.ALLOWED_DOMAINS:
        assert domain not in ("vk.com", "vk.ru", "vk.me")
        assert not domain.endswith(("vk.com", "vk.ru"))


SCRIPT = textwrap.dedent("""
    import json, socket, sys, urllib.request
    sys.path.insert(0, {root!r})
    from vkbackup import firewall, net
    firewall.install()
    results = {{}}
    def attempt(name, fn):
        try:
            fn()
            results[name] = "ok"
        except firewall.BlockedConnection:
            results[name] = "blocked"
        except Exception as e:  # обёртки urllib прячут причину в reason
            results[name] = "blocked" if isinstance(getattr(e, "reason", None), firewall.BlockedConnection) else type(e).__name__
    attempt("dns", lambda: socket.getaddrinfo("example.org", 443))
    attempt("urllib", lambda: urllib.request.urlopen("https://example.org", timeout=3))
    attempt("raw_ip", lambda: socket.create_connection(("1.1.1.1", 443), timeout=3))
    attempt("udp", lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", ("8.8.8.8", 53)))
    attempt("lookalike", lambda: socket.getaddrinfo("userapi.com.evil.ru", 443))
    attempt("vk_api", lambda: socket.getaddrinfo("api.vk.com", 443))
    attempt("net_redirect_target", lambda: net.download("https://example.org/x.jpg", __import__("pathlib").Path("x")))
    attempt("loopback", lambda: socket.getaddrinfo("127.0.0.1", 80))
    attempt("localhost", lambda: socket.getaddrinfo("localhost", 80))
    print(json.dumps({{"results": results, "blocked": len(firewall.snapshot()["blocked"])}}))
""")


def test_lock_blocks_everything_but_vk_storage(tmp_path):
    proc = subprocess.run([sys.executable, "-I", "-c", SCRIPT.format(root=str(ROOT))],
                          capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    r = data["results"]
    for name in ("dns", "urllib", "raw_ip", "udp", "lookalike", "vk_api", "net_redirect_target"):
        assert r[name] == "blocked", (name, r)
    assert r["loopback"] == "ok" and r["localhost"] == "ok"
    assert data["blocked"] >= 7


def test_lock_writes_journal(tmp_path):
    script = textwrap.dedent(f"""
        import socket, sys
        sys.path.insert(0, {str(ROOT)!r})
        from pathlib import Path
        from vkbackup import firewall
        firewall.install(Path({str(tmp_path)!r}))
        try:
            socket.getaddrinfo("tracker.example.com", 443)
        except firewall.BlockedConnection:
            pass
    """)
    subprocess.run([sys.executable, "-I", "-c", script], check=True, timeout=60)
    journal = (tmp_path / "network.log").read_text(encoding="utf-8")
    assert "замок включён" in journal
    assert "ЗАБЛОКИРОВАНО" in journal and "tracker.example.com" in journal
