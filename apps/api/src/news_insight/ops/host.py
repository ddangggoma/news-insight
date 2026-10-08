"""Host health the containers cannot see (2026-10-08): macOS memory and swap, and the local Qwen.

The Mac ran out of memory twice (10-05 jetsam, 10-06 the Docker VM died) and the console said
nothing. The host card job (`scripts/dev.sh cards`, every 10 min) records a snapshot in Redis;
the API shows it on the dashboard and the ops check warns from it.
"""

import json
import re
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import redis

KEY = "ops:host"
TTL_SECONDS = 3600
STALE = timedelta(minutes=30)
SWAP = re.compile(r"total = ([\d.]+)M\s+used = ([\d.]+)M")
FREE = re.compile(r"free percentage: (\d+)%")
Runner = Callable[..., subprocess.CompletedProcess[str]]


def _run(runner: Runner, args: list[str]) -> str:
    try:
        return runner(args, capture_output=True, text=True, timeout=30, check=False).stdout or ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def collect(
    *,
    lm_url: str,
    lm_model: str,
    now: datetime,
    runner: Runner = subprocess.run,
    http: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {"captured_at": now.isoformat()}
    if match := SWAP.search(_run(runner, ["sysctl", "-n", "vm.swapusage"])):
        snapshot["swap_total_mb"] = round(float(match[1]))
        snapshot["swap_used_mb"] = round(float(match[2]))
    if match := FREE.search(_run(runner, ["memory_pressure"])):
        snapshot["memory_free_pct"] = int(match[1])
    get = http or (lambda url: httpx.get(url, timeout=5).json())
    try:
        model = get(f"{lm_url.rstrip('/')}/api/v0/models/{lm_model}")
        snapshot["qwen"] = {
            "model": lm_model,
            "state": model.get("state"),
            "context": model.get("loaded_context_length"),
        }
    except (httpx.HTTPError, ValueError, AttributeError):
        snapshot["qwen"] = {"model": lm_model, "state": "unreachable", "context": None}
    return snapshot


def save(client: redis.Redis, snapshot: dict[str, Any]) -> None:
    client.set(KEY, json.dumps(snapshot), ex=TTL_SECONDS)


def load(client: redis.Redis, *, now: datetime) -> dict[str, Any] | None:
    """The latest snapshot with `stale` set when the host job has not reported for 30 minutes."""
    try:
        raw = client.get(KEY)
    except redis.RedisError:
        return None
    if not raw:
        return None
    snapshot: dict[str, Any] = json.loads(raw)  # type: ignore[arg-type]
    captured = datetime.fromisoformat(snapshot["captured_at"]).astimezone(UTC)
    snapshot["stale"] = now - captured > STALE
    return snapshot


def swap_ratio(snapshot: dict[str, Any]) -> float | None:
    total, used = snapshot.get("swap_total_mb"), snapshot.get("swap_used_mb")
    return used / total if total and used is not None else None
