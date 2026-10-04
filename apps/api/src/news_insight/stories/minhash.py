"""MinHash signatures over character 3-grams, with LSH banding (64 = 16 bands x 4 rows).

Korean card titles give a shared language across sources, so near-duplicate and same-event
detection works for translated reports too. Pure Python: ~3k hash ops per item.
"""

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from news_insight.content.normalize import canonical_url

NUM_PERM = 64
BANDS = 16
ROWS = NUM_PERM // BANDS
PRIME = (1 << 61) - 1
MASK63 = (1 << 63) - 1
SHINGLE = 3
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


def _h64(data: bytes) -> int:
    return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")


PARAMS: tuple[tuple[int, int], ...] = tuple(
    (_h64(f"a{i}".encode()) % (PRIME - 1) + 1, _h64(f"b{i}".encode()) % PRIME)
    for i in range(NUM_PERM)
)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return _NON_WORD.sub(" ", text).strip()


def shingles(text: str) -> set[int]:
    compact = normalize_text(text).replace(" ", "")
    if len(compact) < SHINGLE:
        return {_h64(compact.encode())} if compact else set()
    return {_h64(compact[i : i + SHINGLE].encode()) for i in range(len(compact) - SHINGLE + 1)}


def signature(values: set[int]) -> list[int]:
    if not values:
        return [MASK63] * NUM_PERM
    return [min((a * x + b) % PRIME for x in values) for a, b in PARAMS]


def band_hashes(sig: list[int]) -> list[int]:
    out = []
    for band in range(BANDS):
        chunk = sig[band * ROWS : (band + 1) * ROWS]
        out.append(_h64(b"".join(v.to_bytes(8, "big") for v in chunk)) & MASK63)
    return out


def similarity(left: list[int], right: list[int]) -> float:
    return sum(1 for a, b in zip(left, right, strict=True) if a == b) / NUM_PERM


MOBILE_PREFIXES = ("m.", "mobile.", "amp.")
AMP_PARAMS = frozenset({"amp", "outputtype", "output", "amp_js_v"})


def dedup_url(url: str) -> str:
    """canonical_url plus AMP / mobile unification, for exact-duplicate matching only."""
    parts = urlsplit(canonical_url(url))
    host = parts.netloc
    for prefix in MOBILE_PREFIXES:
        if host.startswith(prefix):
            host = host[len(prefix) :]
            break
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/amp/?$", "", parts.path)
    path = re.sub(r"^/amp/", "/", path).rstrip("/") or "/"
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in AMP_PARAMS])
    return urlunsplit(("https", host, path, query, ""))
