"""Exercise the suite boundary without contacting any external host."""
import asyncio
import socket

import pytest

from conftest import ExternalNetworkBlocked, _loopback_host, install_network_guard


@pytest.mark.parametrize("host", ["127.0.0.1", "127.12.3.4", "::1", "::ffff:127.0.0.1", "localhost", b"localhost"])
def test_loopback_addresses_are_recognized(host):
    assert _loopback_host(host)


@pytest.mark.parametrize("host", ["192.0.2.1", "2001:db8::1", "synthetic-secret.invalid", "127.0.0.1.invalid", b"\xff", "", 123])
def test_external_or_ambiguous_addresses_are_rejected(host):
    assert not _loopback_host(host)


@pytest.mark.parametrize("operation", ["getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"])
def test_external_dns_is_blocked_before_resolver(monkeypatch, operation):
    calls = []
    monkeypatch.setattr(socket, operation, lambda *args, **kwargs: calls.append(args))
    blocked = install_network_guard(monkeypatch)
    with pytest.raises(ExternalNetworkBlocked) as error:
        getattr(socket, operation)("SYNTHETIC-private-host.invalid")
    assert "SYNTHETIC" not in str(error.value)
    assert blocked == [operation]
    assert not calls


@pytest.mark.parametrize("method", ["connect", "connect_ex"])
@pytest.mark.parametrize("family,address", [(socket.AF_INET, ("192.0.2.1", 443)), (socket.AF_INET6, ("2001:db8::1", 443, 0, 0))])
def test_external_tcp_is_blocked_before_socket_io(monkeypatch, method, family, address):
    calls = []
    monkeypatch.setattr(socket.socket, method, lambda *args: calls.append(args))
    blocked = install_network_guard(monkeypatch)
    with socket.socket(family) as sock:
        with pytest.raises(ExternalNetworkBlocked):
            getattr(sock, method)(address)
    assert blocked == [method]
    assert not calls


def test_real_ipv4_loopback_connection_and_dns():
    assert socket.getaddrinfo("localhost", 0)
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.create_connection(server.getsockname(), timeout=1) as client:
            accepted, _ = server.accept()
            with accepted:
                client.sendall(b"synthetic")
                assert accepted.recv(9) == b"synthetic"


def test_real_socketpair_remains_available():
    left, right = socket.socketpair()
    with left, right:
        left.sendall(b"synthetic")
        assert right.recv(9) == b"synthetic"


@pytest.mark.asyncio
async def test_event_loop_selfpipe_and_fake_transports_remain_available():
    done = asyncio.Event()
    asyncio.get_running_loop().call_soon(done.set)
    await asyncio.wait_for(done.wait(), timeout=1)


def test_external_reverse_dns_is_blocked_before_resolver(monkeypatch):
    calls = []
    monkeypatch.setattr(socket, "getnameinfo", lambda *args: calls.append(args))
    blocked = install_network_guard(monkeypatch)
    with pytest.raises(ExternalNetworkBlocked):
        socket.getnameinfo(("192.0.2.1", 443), 0)
    assert blocked == ["getnameinfo"]
    assert not calls


@pytest.mark.parametrize("with_flags", [False, True])
def test_external_udp_is_blocked_before_sendto(monkeypatch, with_flags):
    calls = []
    monkeypatch.setattr(socket.socket, "sendto", lambda *args: calls.append(args))
    blocked = install_network_guard(monkeypatch)
    address = ("192.0.2.1", 53)
    args = (0, address) if with_flags else (address,)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        with pytest.raises(ExternalNetworkBlocked):
            sock.sendto(b"synthetic", *args)
    assert blocked == ["sendto"]
    assert not calls


def test_swallowed_external_attempt_still_fails_test_teardown(tmp_path):
    """Child process explicitly loads the guard; its resolver is fake as backup."""
    from pathlib import Path
    import subprocess
    import sys

    source = Path(__file__).with_name("conftest.py").read_text(encoding="utf-8")
    # Even a broken guard cannot reach a real resolver in this negative check.
    source += '\ndef backup_resolver(*args, **kwargs):\n    raise AssertionError("synthetic resolver")\nsocket.getaddrinfo = backup_resolver\n'
    (tmp_path / "conftest.py").write_text(source, encoding="utf-8")
    (tmp_path / "test_swallowed.py").write_text(
        'import socket\ndef test_swallowed():\n    try:\n        socket.getaddrinfo("synthetic.invalid", 443)\n    except AssertionError:\n        pass\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "--confcutdir", str(tmp_path), str(tmp_path / "test_swallowed.py")],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1
    assert "Unmocked external network operation attempted during test" in result.stdout
    assert "synthetic.invalid" not in result.stdout + result.stderr
