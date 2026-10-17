#!/usr/bin/env python3
"""Edge proxy: the site's public ports on this Mac, with each visitor's address passed to Caddy.

Docker Desktop publishes a port through its own backend process, so every connection reaches the
container from a VM address (192.168.65.1, or the network gateway for a loopback port): the
rate limits, login records and access log all saw one visitor. This process owns the public
ports instead and relays each connection to Caddy's loopback-only ports, starting with a PROXY
protocol v2 header that carries the visitor's address. Caddy trusts that header from the gateway
alone (ops/Caddyfile, ops/caddy/start.sh), and only this Mac can reach the loopback ports.

Standard library only and Python 3.9, so launchd runs it on the system python3
(scripts/install-edge-proxy.sh, docs/runbooks/operations.md §13):

    /usr/bin/python3 ops/edge/proxy.py 8700=127.0.0.1:8702 8701=127.0.0.1:8703
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import logging
import resource
import signal
import socket
import struct
import sys
import time

SIGNATURE = b"\r\n\r\n\x00\r\nQUIT\n"
CHUNK = 64 * 1024
CONNECT_TIMEOUT = 5.0
# After one side has closed, how long the other may keep sending before both are dropped.
# Caddy closes idle connections itself; this frees the ones whose visitor vanished.
CLOSE_GRACE = 60.0
BIND_RETRY = 2.0
REPORT_EVERY = 3600.0
FAILURE_LOG_EVERY = 60.0

log = logging.getLogger("edge")
Address = tuple[str, int]  # builtin generics work at runtime from 3.9


def proxy_header(source: Address, destination: Address) -> bytes:
    """PROXY protocol v2 header for a TCP connection from ``source`` to ``destination``."""
    src = _plain(source[0])
    dst = _plain(destination[0])
    if src.version != dst.version:
        # the header holds one family: keep the visitor's address, which is what Caddy reads
        dst = ipaddress.ip_address("::" if src.version == 6 else "0.0.0.0")
    family = 0x11 if src.version == 4 else 0x21  # AF_INET or AF_INET6, over STREAM
    body = src.packed + dst.packed + struct.pack("!HH", source[1], destination[1])
    return SIGNATURE + bytes((0x21, family)) + struct.pack("!H", len(body)) + body


def _plain(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    address = ipaddress.ip_address(host.split("%", 1)[0])  # drop an IPv6 zone (fe80::1%en0)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def parse_route(text: str) -> tuple[int, Address]:
    """``8700=127.0.0.1:8702`` -> (8700, ("127.0.0.1", 8702))."""
    port, _, target = text.partition("=")
    host, _, upstream = target.rpartition(":")
    if not (port.isdigit() and upstream.isdigit() and host):
        raise argparse.ArgumentTypeError(f"expected LISTEN_PORT=HOST:PORT, got {text!r}")
    return int(port), (host.strip("[]"), int(upstream))


class Stats:
    def __init__(self) -> None:
        self.active = 0
        self.served = 0
        self.refused = 0
        self.failed: dict[Address, int] = {}
        self._last_failure_log: dict[Address, float] = {}

    def upstream_failed(self, upstream: Address, error: BaseException) -> None:
        count = self.failed[upstream] = self.failed.get(upstream, 0) + 1
        now = time.monotonic()
        if now - self._last_failure_log.get(upstream, -FAILURE_LOG_EVERY) >= FAILURE_LOG_EVERY:
            self._last_failure_log[upstream] = now
            log.warning(
                "cannot reach Caddy at %s:%d (%s); %d failed so far",
                upstream[0],
                upstream[1],
                str(error) or type(error).__name__,  # a timeout has no message
                count,
            )

    def report(self) -> None:
        if self.served or self.refused or self.failed:
            failed = sum(self.failed.values())
            log.info(
                "last hour: %d connections, %d refused (limit), %d upstream failures; %d open",
                self.served,
                self.refused,
                failed,
                self.active,
            )
        self.served = self.refused = 0
        self.failed.clear()


class EdgeProxy:
    def __init__(self, routes: list[tuple[int, Address]], host: str | None, limit: int) -> None:
        self.routes = routes
        self.host = host
        self.limit = limit
        self.stats = Stats()
        self.servers: list[asyncio.base_events.Server] = []

    async def serve(self, stop: asyncio.Event) -> None:
        binders = [
            asyncio.ensure_future(self._bind(port, upstream)) for port, upstream in self.routes
        ]
        reporter = asyncio.ensure_future(self._report())
        await stop.wait()
        for task in binders + [reporter]:
            task.cancel()
        # stop listening; open connections are dropped when the loop ends
        for server in self.servers:
            server.close()
        log.info("stopped")

    async def _bind(self, port: int, upstream: Address) -> None:
        logged = None
        while True:
            try:
                server = await asyncio.start_server(
                    lambda r, w: self._relay(r, w, upstream),
                    host=self.host,
                    port=port,
                    backlog=512,
                )
            except OSError as error:
                # during the switch-over Docker still holds the port (EADDRINUSE): take it
                # once released
                if error.errno != logged:
                    log.warning(
                        "cannot listen on %d (%s); retrying every %.0f s",
                        port,
                        error.strerror or error,
                        BIND_RETRY,
                    )
                    logged = error.errno
                await asyncio.sleep(BIND_RETRY)
                continue
            self.servers.append(server)
            log.info("listening on %d -> %s:%d", port, upstream[0], upstream[1])
            return

    async def _report(self) -> None:
        while True:
            await asyncio.sleep(REPORT_EVERY)
            self.stats.report()

    async def _relay(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream: Address,
    ) -> None:
        if self.stats.active >= self.limit:
            self.stats.refused += 1
            client_writer.close()
            return
        self.stats.active += 1
        self.stats.served += 1
        writers = [client_writer]
        try:
            sock = client_writer.get_extra_info("socket")
            if sock is not None:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            peer = client_writer.get_extra_info("peername")
            local = client_writer.get_extra_info("sockname")
            try:
                up_reader, up_writer = await asyncio.wait_for(
                    asyncio.open_connection(*upstream), CONNECT_TIMEOUT
                )
            # asyncio.TimeoutError is not the builtin one before 3.11
            except (OSError, asyncio.TimeoutError) as error:  # noqa: UP041
                self.stats.upstream_failed(upstream, error)
                return
            writers.append(up_writer)
            up_writer.write(proxy_header(peer[:2], local[:2]))
            await _join(_pipe(client_reader, up_writer), _pipe(up_reader, client_writer))
        except Exception:  # noqa: BLE001 - one broken connection must not stop the proxy
            log.exception("connection failed")
        finally:
            self.stats.active -= 1
            for writer in writers:
                writer.close()


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while True:
        data = await reader.read(CHUNK)
        if not data:
            break
        writer.write(data)
        await writer.drain()
    # pass the half-close on: the other direction may still be sending
    if writer.can_write_eof() and not writer.is_closing():
        writer.write_eof()


async def _join(*pipes) -> None:
    """Run both directions; stop both on an error, or CLOSE_GRACE after the first one ends."""
    tasks = [asyncio.ensure_future(pipe) for pipe in pipes]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        failed = any(not task.cancelled() and task.exception() for task in done)
        if pending and not failed:
            await asyncio.wait(pending, timeout=CLOSE_GRACE)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def raise_file_limit(wanted: int = 8192) -> int:
    """launchd starts jobs with 256 open files; each relayed connection needs two."""
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = wanted if hard == resource.RLIM_INFINITY else min(wanted, hard)
    if target > soft:
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
            soft = target
        except (ValueError, OSError):
            pass
    return soft


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("routes", nargs="+", type=parse_route, metavar="LISTEN_PORT=HOST:PORT")
    parser.add_argument("--host", default=None, help="listen address (default: all, IPv4 and IPv6)")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s edge %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    limit = max(64, (min(raise_file_limit(), 8192) - 64) // 2)
    log.info("starting: up to %d connections at once", limit)

    async def run() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        await EdgeProxy(args.routes, args.host, limit).serve(stop)

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
