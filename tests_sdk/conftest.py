"""Default-suite runtime network boundary: fake transports or loopback only.

This fixture does not govern collection, subprocesses or non-socket native I/O.
Standalone public-live/runtime scripts remain separate explicit checks.
"""
import ipaddress
import socket

import pytest


class ExternalNetworkBlocked(AssertionError):
    """An unmocked external network operation reached the test boundary."""


def _loopback_host(host, *, allow_none=False):
    if host is None:
        return allow_none
    if isinstance(host, bytes):
        try:
            host = host.decode("ascii")
        except UnicodeDecodeError:
            return False
    if not isinstance(host, str):
        return False
    if host.lower() in {"localhost", "localhost."}:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or (
        isinstance(address, ipaddress.IPv6Address)
        and address.ipv4_mapped is not None
        and address.ipv4_mapped.is_loopback
    )


def install_network_guard(monkeypatch):
    """Install a per-test guard and return sanitized blocked-operation names."""
    blocked = []

    def reject(operation):
        blocked.append(operation)
        raise ExternalNetworkBlocked("Unmocked external network operation blocked")

    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        original = getattr(socket, name)

        def resolve(host, *args, _original=original, _name=name, **kwargs):
            if not _loopback_host(host, allow_none=_name == "getaddrinfo"):
                reject(_name)
            return _original(host, *args, **kwargs)

        monkeypatch.setattr(socket, name, resolve)

    def allowed_address(sock, address):
        if sock.family == getattr(socket, "AF_UNIX", None):
            return True
        return (sock.family in (socket.AF_INET, socket.AF_INET6)
                and isinstance(address, tuple) and bool(address)
                and _loopback_host(address[0]))

    for name in ("connect", "connect_ex"):
        original = getattr(socket.socket, name)

        def connect(sock, address, _original=original, _name=name):
            if not allowed_address(sock, address):
                reject(_name)
            return _original(sock, address)

        monkeypatch.setattr(socket.socket, name, connect)

    original_sendto = socket.socket.sendto

    def sendto(sock, data, *args):
        # socket.sendto(data, address) and socket.sendto(data, flags, address).
        if not args or not allowed_address(sock, args[-1]):
            reject("sendto")
        return original_sendto(sock, data, *args)

    monkeypatch.setattr(socket.socket, "sendto", sendto)

    original_getnameinfo = socket.getnameinfo

    def getnameinfo(address, flags):
        if not isinstance(address, tuple) or not address or not _loopback_host(address[0]):
            reject("getnameinfo")
        return original_getnameinfo(address, flags)

    monkeypatch.setattr(socket, "getnameinfo", getnameinfo)
    return blocked


@pytest.fixture(autouse=True)
def external_network_guard(monkeypatch):
    blocked = install_network_guard(monkeypatch)
    yield blocked
    if blocked:
        pytest.fail("Unmocked external network operation attempted during test", pytrace=False)
