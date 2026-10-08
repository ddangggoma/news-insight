"""The classification schemes as the pipeline reads them at run time (plan 15-2).

`current()` loads the active schemes and nodes from the database and keeps them until a newer
revision is applied (checked at most every RECHECK seconds). Without schemes in the database
(a fresh install, most tests) it falls back to the code catalog, so classification never
depends on the seed having run.
"""

import threading
import time
from dataclasses import dataclass, field
from functools import cached_property

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.taxonomy.catalog import (
    DEFINITIONS,
    FIELDS,
    IMPACTS,
    SCHEME_LEADS,
    SCOPES,
    SIGNAL_TYPES,
)

BUILTIN = ("technology", "signal_type", "impact", "scope")  # schemes with item_cards columns
RECHECK = 60.0


@dataclass(frozen=True)
class RNode:
    key: str
    label: str
    parent: str | None
    depth: int
    definition: str | None = None
    include: str | None = None
    exclude: str | None = None


@dataclass(frozen=True)
class RScheme:
    key: str
    name: str
    structure: str = "tree"
    min_labels: int = 0
    max_labels: int = 3
    llm_depth: int | None = None
    description: str | None = None
    assign: tuple[str, ...] = ("llm",)
    nodes: tuple[RNode, ...] = ()

    @cached_property
    def by_key(self) -> dict[str, RNode]:
        return {node.key: node for node in self.nodes}

    @cached_property
    def children(self) -> dict[str | None, list[RNode]]:
        out: dict[str | None, list[RNode]] = {}
        for node in self.nodes:
            out.setdefault(node.parent, []).append(node)
        return out

    def llm_nodes(self) -> list[RNode]:
        """Nodes the LLM chooses from: down to llm_depth (every depth when unset)."""
        limit = self.llm_depth or 10**6
        return [node for node in self.nodes if node.depth <= limit]

    def root(self, key: str) -> str:
        node = self.by_key[key]
        while node.parent is not None and node.parent in self.by_key:
            node = self.by_key[node.parent]
        return node.key


@dataclass(frozen=True)
class Registry:
    revision: int | None
    schemes: dict[str, RScheme] = field(default_factory=dict)

    def scheme(self, key: str) -> RScheme:
        return self.schemes[key]

    def extra_llm_schemes(self) -> list[RScheme]:
        """Schemes without a card column that the LLM labels (stored in extra_labels)."""
        return [s for s in self.schemes.values() if s.key not in BUILTIN and "llm" in s.assign]


def from_catalog() -> Registry:
    tech = [RNode(f.key, f.name, None, 1) for f in FIELDS] + [
        RNode(t.key, t.name, f.key, 2) for f in FIELDS for t in f.themes
    ]

    def flat(nodes: tuple[object, ...]) -> tuple[RNode, ...]:
        return tuple(
            RNode(n.key, n.name, None, 1, DEFINITIONS.get(n.key))  # type: ignore[attr-defined]
            for n in nodes
        )

    return Registry(
        revision=None,
        schemes={
            "technology": RScheme(
                "technology", "기술", "tree", 0, 2, 2, None, ("llm", "rule", "derived"), tuple(tech)
            ),
            "signal_type": RScheme(
                "signal_type", "신호 유형", "list", 1, 1, 1, nodes=flat(SIGNAL_TYPES)
            ),
            "impact": RScheme(
                "impact", "영향", "list", 1, 1, 1, SCHEME_LEADS["impact"], nodes=flat(IMPACTS)
            ),
            "scope": RScheme(
                "scope", "범위", "list", 1, 1, 1, SCHEME_LEADS["scope"], nodes=flat(SCOPES)
            ),
        },
    )


def load(session: Session) -> Registry:
    from news_insight.taxonomy.models import TaxNode, TaxRevision, TaxScheme

    schemes = list(
        session.scalars(
            select(TaxScheme)
            .where(TaxScheme.status == "active")
            .order_by(TaxScheme.sort, TaxScheme.id)
        )
    )
    if not schemes:
        return from_catalog()
    revision = session.scalar(
        select(func.max(TaxRevision.id)).where(TaxRevision.status == "applied")
    )
    nodes = list(
        session.scalars(
            select(TaxNode)
            .where(TaxNode.status == "active")
            .order_by(TaxNode.depth, TaxNode.sort, TaxNode.id)
        )
    )
    keys = {node.id: node.key for node in nodes}
    by_scheme: dict[int, list[RNode]] = {}
    for node in nodes:
        by_scheme.setdefault(node.scheme_id, []).append(
            RNode(
                node.key,
                node.label,
                keys.get(node.parent_id) if node.parent_id else None,
                node.depth,
                node.definition,
                node.include_text,
                node.exclude_text,
            )
        )
    return Registry(
        revision=revision,
        schemes={
            s.key: RScheme(
                s.key,
                s.name,
                s.structure,
                s.min_labels,
                s.max_labels,
                s.llm_depth,
                s.description,
                tuple(s.assign or ["llm"]),
                tuple(by_scheme.get(s.id, [])),
            )
            for s in schemes
        },
    )


_lock = threading.Lock()
_cached: Registry | None = None
_checked = 0.0
_override: Registry | None = None


def _latest_revision(session: Session) -> int | None:
    from news_insight.taxonomy.models import TaxRevision, TaxScheme

    if session.scalar(select(func.count()).select_from(TaxScheme)) == 0:
        return None
    return session.scalar(select(func.max(TaxRevision.id)).where(TaxRevision.status == "applied"))


def current(session: Session | None = None) -> Registry:
    """The registry for this process; reloaded when a newer revision is applied."""
    global _cached, _checked
    if _override is not None:
        return _override
    now = time.monotonic()
    with _lock:
        if _cached is not None and now - _checked < RECHECK:
            return _cached
    try:
        if session is not None:
            registry = _refresh(session)
        else:
            from news_insight.db import session_scope

            with session_scope() as own:
                registry = _refresh(own)
    except Exception:  # noqa: BLE001 - no database (unit tests, tooling): the code catalog
        registry = _cached or from_catalog()
    with _lock:
        _cached, _checked = registry, now
    return registry


def _refresh(session: Session) -> Registry:
    latest = _latest_revision(session)
    if _cached is not None and latest is not None and _cached.revision == latest:
        return _cached
    return load(session) if latest is not None else from_catalog()


def use(registry: Registry | None) -> None:
    """Pin a registry (tests) or unpin it with None; also forgets the cached one."""
    global _override, _cached, _checked
    with _lock:
        _override, _cached, _checked = registry, None, 0.0
