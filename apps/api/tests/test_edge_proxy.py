"""The edge proxy on the Mac (ops/edge/proxy.py): PROXY v2 headers, relaying, port takeover."""

import ast
import asyncio
import importlib.util
import ipaddress
import socket
import struct
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROXY_PATH = Path(__file__).resolve().parents[3] / "ops" / "edge" / "proxy.py"


def load_proxy() -> ModuleType:
    spec = importlib.util.spec_from_file_location("edge_proxy", PROXY_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["edge_proxy"] = module
    spec.loader.exec_module(module)
    return module


edge = load_proxy()


def parse_header(data: bytes) -> tuple[str, int, str, int, int]:
    """(source, source port, destination, destination port, header length) of a v2 header."""
    assert data[:12] == edge.SIGNATURE
    assert data[12] == 0x21  # version 2, PROXY command
    family = data[13]
    (length,) = struct.unpack("!H", data[14:16])
    body = data[16 : 16 + length]
    size = 4 if family == 0x11 else 16
    assert family in (0x11, 0x21)
    src = str(ipaddress.ip_address(body[:size]))
    dst = str(ipaddress.ip_address(body[size : 2 * size]))
    sport, dport = struct.unpack("!HH", body[2 * size : 2 * size + 4])
    return src, sport, dst, dport, 16 + length


def test_runs_on_the_system_python() -> None:
    # launchd runs it with /usr/bin/python3 (3.9 on macOS, no packages); this suite runs on 3.12
    tree = ast.parse(PROXY_PATH.read_text(encoding="utf-8"), feature_version=(3, 9))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert imported <= sys.stdlib_module_names


def test_ipv4_header_layout() -> None:
    header = edge.proxy_header(("203.0.113.7", 51234), ("10.0.0.2", 8700))

    assert header == (
        edge.SIGNATURE
        + bytes((0x21, 0x11, 0, 12))
        + bytes((203, 0, 113, 7, 10, 0, 0, 2))
        + struct.pack("!HH", 51234, 8700)
    )


def test_ipv6_header() -> None:
    header = edge.proxy_header(("2001:db8::1", 4000), ("2001:db8::2", 8701))

    assert header[13] == 0x21
    assert parse_header(header)[:4] == ("2001:db8::1", 4000, "2001:db8::2", 8701)


def test_ipv4_mapped_and_zoned_addresses_are_plain() -> None:
    mapped = edge.proxy_header(("::ffff:198.51.100.9", 1), ("::ffff:10.0.0.2", 2))
    zoned = edge.proxy_header(("fe80::1%en0", 1), ("fe80::2%en0", 2))

    assert parse_header(mapped)[:4] == ("198.51.100.9", 1, "10.0.0.2", 2)
    assert parse_header(zoned)[:4] == ("fe80::1", 1, "fe80::2", 2)


def test_mixed_families_keep_the_visitor() -> None:
    header = edge.proxy_header(("2001:db8::1", 1), ("10.0.0.2", 2))

    assert parse_header(header)[:4] == ("2001:db8::1", 1, "::", 2)


def test_routes() -> None:
    assert edge.parse_route("8700=127.0.0.1:8702") == (8700, ("127.0.0.1", 8702))
    assert edge.parse_route("8701=[::1]:8703") == (8701, ("::1", 8703))
    with pytest.raises(Exception, match="LISTEN_PORT=HOST:PORT"):
        edge.parse_route("8700:8702")


class Upstream:
    """Stands in for Caddy: reads the PROXY header, then answers in upper case until EOF."""

    def __init__(self) -> None:
        self.headers: list[tuple[str, int, str, int]] = []
        self.bodies: list[bytes] = []

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        start = await reader.readexactly(16)
        rest = await reader.readexactly(struct.unpack("!H", start[14:16])[0])
        self.headers.append(parse_header(start + rest)[:4])
        body = await reader.read()  # until the client's half-close
        self.bodies.append(body)
        writer.write(body.upper())
        await writer.drain()
        writer.close()


async def started(proxy, stop: asyncio.Event) -> tuple[asyncio.Task, int]:
    task = asyncio.ensure_future(proxy.serve(stop))
    for _ in range(200):
        if proxy.servers:
            return task, proxy.servers[0].sockets[0].getsockname()[1]
        await asyncio.sleep(0.01)
    raise AssertionError("proxy did not listen")


def test_relays_with_the_visitor_address_and_half_close() -> None:
    async def run() -> None:
        upstream = Upstream()
        server = await asyncio.start_server(upstream.handle, "127.0.0.1", 0)
        up_port = server.sockets[0].getsockname()[1]
        stop = asyncio.Event()
        proxy = edge.EdgeProxy([(0, ("127.0.0.1", up_port))], "127.0.0.1", limit=10)
        task, port = await started(proxy, stop)

        payload = bytes(range(256)) * 4096  # 1 MiB, every byte value
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        client_port = writer.get_extra_info("sockname")[1]
        writer.write(payload)
        writer.write_eof()  # the answer must still come back after our half-close
        answer = await asyncio.wait_for(reader.read(), 10)
        writer.close()

        assert answer == payload.upper()
        assert upstream.bodies == [payload]
        assert upstream.headers == [("127.0.0.1", client_port, "127.0.0.1", port)]
        for _ in range(100):
            if proxy.stats.active == 0:
                break
            await asyncio.sleep(0.01)
        assert (proxy.stats.served, proxy.stats.active) == (1, 0)
        stop.set()
        await task
        server.close()

    asyncio.run(run())


def test_closes_the_visitor_when_caddy_is_down() -> None:
    async def run() -> None:
        with socket.socket() as probe:  # a port nothing listens on
            probe.bind(("127.0.0.1", 0))
            dead = probe.getsockname()[1]
        stop = asyncio.Event()
        proxy = edge.EdgeProxy([(0, ("127.0.0.1", dead))], "127.0.0.1", limit=10)
        task, port = await started(proxy, stop)

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        assert await asyncio.wait_for(reader.read(), 10) == b""
        writer.close()
        assert proxy.stats.failed == {("127.0.0.1", dead): 1}
        stop.set()
        await task

    asyncio.run(run())


def test_refuses_connections_over_the_limit() -> None:
    async def run() -> None:
        hold = asyncio.Event()

        async def slow(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            await hold.wait()
            writer.close()

        server = await asyncio.start_server(slow, "127.0.0.1", 0)
        up_port = server.sockets[0].getsockname()[1]
        stop = asyncio.Event()
        proxy = edge.EdgeProxy([(0, ("127.0.0.1", up_port))], "127.0.0.1", limit=1)
        task, port = await started(proxy, stop)

        first = await asyncio.open_connection("127.0.0.1", port)
        for _ in range(100):
            if proxy.stats.active:
                break
            await asyncio.sleep(0.01)
        second_reader, second_writer = await asyncio.open_connection("127.0.0.1", port)
        assert await asyncio.wait_for(second_reader.read(), 10) == b""
        assert proxy.stats.refused == 1
        hold.set()
        first[1].close()
        second_writer.close()
        stop.set()
        await task
        server.close()

    asyncio.run(run())


def test_takes_the_port_once_docker_lets_go(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(edge, "BIND_RETRY", 0.05)

    async def run() -> None:
        holder = socket.socket()
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        port = holder.getsockname()[1]
        stop = asyncio.Event()
        proxy = edge.EdgeProxy([(port, ("127.0.0.1", 9))], "127.0.0.1", limit=10)
        task = asyncio.ensure_future(proxy.serve(stop))
        await asyncio.sleep(0.2)
        assert proxy.servers == []  # still waiting

        holder.close()
        for _ in range(100):
            if proxy.servers:
                break
            await asyncio.sleep(0.02)
        assert proxy.servers[0].sockets[0].getsockname()[1] == port
        stop.set()
        await task

    asyncio.run(run())
