"""Seed the schemes and nodes from the code taxonomy and the technology registry (plan 15-1).

Until the console edits schemes (plan 15-3), the code catalog (fields, themes, signal types,
impacts, scopes) and the `technologies` table stay the source; seeding is idempotent, keeps
nodes edited in the console, and records a revision whenever it changes something.
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from news_insight.taxonomy.catalog import FIELDS, IMPACTS, SCOPES, SIGNAL_TYPES, TAXONOMY_REVISION
from news_insight.taxonomy.models import TaxNode, TaxRevision, TaxScheme
from news_insight.technologies.catalog import TechStatus
from news_insight.technologies.models import Technology, TechnologyAlias

TECHNOLOGY = "technology"
SCHEMES: tuple[dict[str, Any], ...] = (
    {
        "key": TECHNOLOGY,
        "name": "기술",
        "structure": "tree",
        "max_labels": 2,
        "llm_depth": 2,
        "level_names": ["분야", "테마", "기술"],
        "uses": ["radar", "filters", "watch", "briefing", "personas"],
        "sort": 0,
    },
    {
        "key": "signal_type",
        "name": "신호 유형",
        "structure": "list",
        "min_labels": 1,
        "max_labels": 1,
        "llm_depth": 1,
        "uses": ["radar", "filters"],
        "sort": 1,
    },
    {
        "key": "impact",
        "name": "영향",
        "structure": "list",
        "min_labels": 1,
        "max_labels": 1,
        "llm_depth": 1,
        "uses": ["filters", "briefing"],
        "sort": 2,
    },
    {
        "key": "scope",
        "name": "범위",
        "structure": "list",
        "min_labels": 1,
        "max_labels": 1,
        "llm_depth": 1,
        "uses": ["filters"],
        "sort": 3,
    },
)


@dataclass
class SeedResult:
    created: int = 0
    updated: int = 0
    revision_id: int | None = None
    skipped: list[str] = field(default_factory=list)  # technologies whose theme is unknown


@dataclass(frozen=True)
class _Spec:
    key: str
    label: str
    parent: str | None
    sort: int
    aliases: tuple[str, ...] = ()
    attrs: tuple[tuple[str, Any], ...] = ()


def _technology_specs(session: Session) -> list[_Spec]:
    specs: list[_Spec] = []
    for index, f in enumerate(FIELDS):
        specs.append(_Spec(f.key, f.name, None, index))
        specs += [_Spec(t.key, t.name, f.key, i) for i, t in enumerate(f.themes)]
    aliases: dict[str, list[str]] = {}
    for alias, key in session.execute(
        select(TechnologyAlias.alias, TechnologyAlias.technology_key).order_by(
            TechnologyAlias.alias
        )
    ).tuples():
        aliases.setdefault(key, []).append(alias)
    for tech in session.scalars(select(Technology).order_by(Technology.key)):
        if tech.status is TechStatus.IGNORED:
            continue
        attrs = (("kind", tech.kind.value), ("registry_status", tech.status.value))
        specs.append(
            _Spec(tech.key, tech.label, tech.theme_key, 0, tuple(aliases.get(tech.key, [])), attrs)
        )
    return specs


def _list_specs(nodes: tuple[Any, ...]) -> list[_Spec]:
    return [_Spec(node.key, node.name, None, index) for index, node in enumerate(nodes)]


def _upsert_scheme(session: Session, spec: dict[str, Any]) -> tuple[TaxScheme, bool]:
    scheme = session.scalars(select(TaxScheme).where(TaxScheme.key == spec["key"])).one_or_none()
    if scheme is not None:
        return scheme, False
    scheme = TaxScheme(
        key=spec["key"],
        name=spec["name"],
        structure=spec["structure"],
        min_labels=spec.get("min_labels", 0),
        max_labels=spec["max_labels"],
        llm_depth=spec["llm_depth"],
        level_names=spec.get("level_names", []),
        uses=spec["uses"],
        sort=spec["sort"],
    )
    session.add(scheme)
    session.flush()
    return scheme, True


def _sync_nodes(
    session: Session, scheme: TaxScheme, specs: list[_Spec], result: SeedResult
) -> bool:
    existing = {
        n.key: n for n in session.scalars(select(TaxNode).where(TaxNode.scheme_id == scheme.id))
    }
    keys = {spec.key for spec in specs}
    changed = False
    for spec in specs:  # parents come before children in every spec list
        if spec.parent is not None and spec.parent not in keys:
            result.skipped.append(spec.key)
            continue
        node = existing.get(spec.key)
        is_new = node is None
        if node is None:
            node = TaxNode(
                scheme_id=scheme.id, key=spec.key, label=spec.label, aliases=[], attrs={}
            )
            session.add(node)
            existing[spec.key] = node
            result.created += 1
            changed = True
        elif node.edited_in_console:
            continue
        parent_id = existing[spec.parent].id if spec.parent else None
        session.flush()
        wanted = {
            "label": spec.label,
            "parent_id": parent_id,
            "sort": spec.sort,
            "aliases": list(spec.aliases),
            "attrs": dict(spec.attrs),
        }
        if any(getattr(node, name) != value for name, value in wanted.items()):
            result.updated += 0 if is_new else 1
            for name, value in wanted.items():
                setattr(node, name, value)
            changed = True
    session.flush()
    return changed


def rebuild_paths(session: Session, scheme_id: int) -> None:
    nodes = {
        n.id: n for n in session.scalars(select(TaxNode).where(TaxNode.scheme_id == scheme_id))
    }

    def path(node: TaxNode, seen: frozenset[int] = frozenset()) -> list[int]:
        if node.parent_id is None or node.parent_id not in nodes or node.id in seen:
            return [node.id]
        return [*path(nodes[node.parent_id], seen | {node.id}), node.id]

    for node in nodes.values():
        wanted = path(node)
        if node.path != wanted or node.depth != len(wanted):
            node.path, node.depth = wanted, len(wanted)
    session.flush()


def snapshot(session: Session) -> dict[str, Any]:
    schemes = list(session.scalars(select(TaxScheme).order_by(TaxScheme.sort, TaxScheme.id)))
    nodes = list(session.scalars(select(TaxNode).order_by(TaxNode.scheme_id, TaxNode.id)))
    return {
        "schemes": [
            {
                "id": s.id,
                "key": s.key,
                "name": s.name,
                "structure": s.structure,
                "min_labels": s.min_labels,
                "max_labels": s.max_labels,
                "llm_depth": s.llm_depth,
                "level_names": s.level_names,
                "uses": s.uses,
                "sort": s.sort,
                "status": s.status,
            }
            for s in schemes
        ],
        "nodes": [
            {
                "id": n.id,
                "scheme_id": n.scheme_id,
                "parent_id": n.parent_id,
                "key": n.key,
                "label": n.label,
                "definition": n.definition,
                "include_text": n.include_text,
                "exclude_text": n.exclude_text,
                "aliases": n.aliases,
                "attrs": n.attrs,
                "status": n.status,
                "merged_into_id": n.merged_into_id,
                "sort": n.sort,
            }
            for n in nodes
        ],
    }


def seed_taxonomy(session: Session, *, author: str = "seed") -> SeedResult:
    result = SeedResult()
    changed = False
    for spec in SCHEMES:
        scheme, created = _upsert_scheme(session, spec)
        changed |= created
        specs = (
            _technology_specs(session)
            if spec["key"] == TECHNOLOGY
            else _list_specs(
                {"signal_type": SIGNAL_TYPES, "impact": IMPACTS, "scope": SCOPES}[spec["key"]]
            )
        )
        changed |= _sync_nodes(session, scheme, specs, result)
        rebuild_paths(session, scheme.id)
    first = session.scalar(select(TaxRevision.id).limit(1)) is None
    if changed or first:
        revision = TaxRevision(
            author=author,
            note=f"seed from code taxonomy {TAXONOMY_REVISION} and the technology registry",
            status="applied",
            changes=[{"op": "seed", "created": result.created, "updated": result.updated}],
            snapshot=snapshot(session),
        )
        session.add(revision)
        session.flush()
        result.revision_id = revision.id
    return result


# one statement for every card: the trigger's logic, set-based (plan 15-1 backfill)
BACKFILL_SQL = """
WITH v AS (
  SELECT c.item_id, 'technology' AS scheme, t.value AS node
    FROM item_cards c, jsonb_array_elements_text(coalesce(c.themes, '[]'::jsonb)) AS t(value)
  UNION ALL
  SELECT c.item_id, 'technology', t.value
    FROM item_cards c,
         jsonb_array_elements_text(coalesce(c.technology_keys, '[]'::jsonb)) AS t(value)
  UNION ALL
  SELECT item_id, 'technology', field FROM item_cards
    WHERE field IS NOT NULL AND jsonb_array_length(coalesce(themes, '[]'::jsonb)) = 0
  UNION ALL SELECT item_id, 'signal_type', signal_type FROM item_cards WHERE signal_type IS NOT NULL
  UNION ALL SELECT item_id, 'impact', impact FROM item_cards WHERE impact IS NOT NULL
  UNION ALL SELECT item_id, 'scope', scope FROM item_cards WHERE scope IS NOT NULL
)
INSERT INTO card_labels (item_id, node_id, scheme_id, source)
SELECT v.item_id, n.id, n.scheme_id, 'legacy'
FROM v
JOIN tax_schemes s ON s.key = v.scheme
JOIN tax_nodes n ON n.scheme_id = s.id AND n.key = v.node
ON CONFLICT (item_id, node_id) DO NOTHING
"""


def backfill_labels(session: Session) -> int:
    """Rewrite every legacy label from the item_cards columns; returns the label count."""
    session.execute(text("DELETE FROM card_labels WHERE source = 'legacy'"))
    session.execute(text(BACKFILL_SQL))
    return int(
        session.scalar(text("SELECT count(*) FROM card_labels WHERE source = 'legacy'")) or 0
    )
