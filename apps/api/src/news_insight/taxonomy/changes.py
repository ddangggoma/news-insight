"""The console's change engine for schemes and nodes (plan 15-3).

A change set is a list of operations applied in one transaction and recorded as a revision
with what each operation undoes. Preview runs the same operations in a savepoint, measures them
and rolls back, so the numbers it shows are the ones applying would produce.

Cost by operation: renames, definitions, aliases, moves, merges, retirements and relations
need no LLM; a split, a new node within the LLM depth, or a scheme setting change may queue
cards for reclassification (`requeue`), which the classification lane then works through.
"""

from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from news_insight.cards.models import CardRun, ItemCard
from news_insight.taxonomy import registry as taxonomy
from news_insight.taxonomy.models import TaxNode, TaxRelation, TaxRevision, TaxScheme
from news_insight.taxonomy.registry import BUILTIN
from news_insight.taxonomy.seed import rebuild_paths, relabel, snapshot
from news_insight.technologies.catalog import normalize

REQUEUE = "requeue"  # any value but the current revision sends a card back to classification
PROMPT_TOKEN_BUDGET = 6000  # rough share of Qwen's 16K context left to the instructions
KEY_PATTERN = r"^[a-z0-9가-힣][a-z0-9가-힣_\-.]{0,79}$"
LIST_COLUMNS = {"signal_type": "signal_type", "impact": "impact", "scope": "scope"}


class ChangeError(ValueError):
    """An operation that cannot apply (unknown key, cycle, wrong depth...)."""


# ---- operations -------------------------------------------------------------------------------


class CreateNode(BaseModel):
    op: Literal["create_node"]
    scheme: str
    key: str = Field(pattern=KEY_PATTERN)
    label: str = Field(min_length=1, max_length=120)
    parent: str | None = None
    definition: str | None = None
    include_text: str | None = None
    exclude_text: str | None = None
    aliases: list[str] = Field(default_factory=list)
    sort: int = 0
    requeue: bool = False  # within the LLM depth: send the parent's cards back to the LLM


class UpdateNode(BaseModel):
    op: Literal["update_node"]
    scheme: str
    key: str
    label: str | None = Field(default=None, min_length=1, max_length=120)
    definition: str | None = None
    include_text: str | None = None
    exclude_text: str | None = None
    aliases: list[str] | None = None
    sort: int | None = None
    status: Literal["active", "deprecated"] | None = None
    # carding priority (plan 16 #3): 0 제외, 0.5 낮음, 1 보통, 1.5 높음, 2 최우선
    priority: float | None = None

    @field_validator("priority")
    @classmethod
    def _priority(cls, value: float | None) -> float | None:
        if value is not None and value not in (0, 0.5, 1, 1.5, 2):
            raise ValueError("priority is one of 0, 0.5, 1, 1.5, 2")
        return value


class MoveNode(BaseModel):
    op: Literal["move_node"]
    scheme: str
    key: str
    parent: str | None
    requeue: bool = False


class MergeNode(BaseModel):
    op: Literal["merge_node"]
    scheme: str
    key: str
    into: str


class RetireNode(BaseModel):
    op: Literal["retire_node"]
    scheme: str
    key: str
    replacement: str | None = None


class SplitPart(BaseModel):
    key: str = Field(pattern=KEY_PATTERN)
    label: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list)
    definition: str | None = None


class SplitNode(BaseModel):
    op: Literal["split_node"]
    scheme: str
    key: str
    parts: list[SplitPart] = Field(min_length=2, max_length=12)


class CreateScheme(BaseModel):
    op: Literal["create_scheme"]
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    name: str = Field(min_length=1, max_length=80)
    structure: Literal["tree", "list"] = "tree"
    description: str | None = None
    min_labels: int = Field(default=0, ge=0, le=10)
    max_labels: int = Field(default=2, ge=1, le=10)
    llm_depth: int | None = Field(default=1, ge=1, le=10)
    assign: list[Literal["llm", "rule", "derived"]] = Field(
        default_factory=lambda: ["llm"]  # type: ignore[arg-type]
    )
    uses: list[str] = Field(default_factory=lambda: ["filters"])
    level_names: list[str] = Field(default_factory=list)


class UpdateScheme(BaseModel):
    op: Literal["update_scheme"]
    key: str
    name: str | None = None
    description: str | None = None
    min_labels: int | None = Field(default=None, ge=0, le=10)
    max_labels: int | None = Field(default=None, ge=1, le=10)
    llm_depth: int | None = Field(default=None, ge=1, le=10)
    assign: list[Literal["llm", "rule", "derived"]] | None = None
    uses: list[str] | None = None
    level_names: list[str] | None = None
    status: Literal["active", "inactive"] | None = None
    requeue: bool = False  # the LLM part changed: send the scheme's cards back


class Relation(BaseModel):
    op: Literal["add_relation", "remove_relation"]
    from_scheme: str
    from_key: str
    to_scheme: str
    to_key: str
    kind: Literal["implies", "related"] = "implies"


class RestoreColumns(BaseModel):
    """Internal (undo of a merge, retirement or split): put old column values back."""

    op: Literal["restore_columns"]
    rows: list[dict[str, Any]]


Op = Annotated[
    CreateNode
    | UpdateNode
    | MoveNode
    | MergeNode
    | RetireNode
    | SplitNode
    | CreateScheme
    | UpdateScheme
    | Relation
    | RestoreColumns,
    Field(discriminator="op"),
]


class ChangeSet(BaseModel):
    ops: list[Op] = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class OpOutcome(BaseModel):
    op: str
    summary: str
    cards: int = 0  # cards whose labels this operation touches
    requeued: int = 0
    warnings: list[str] = Field(default_factory=list)


class ChangeResult(BaseModel):
    revision_id: int | None
    outcomes: list[OpOutcome]
    affected_cards: int
    requeued_cards: int
    eta_hours: float | None  # at the classification rate of the last 24 hours
    prompt_tokens: int  # rough size of the classification prompt after the change
    prompt_over_budget: bool
    samples: list[dict[str, Any]]


# ---- helpers ----------------------------------------------------------------------------------


class _Run:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.affected: set[int] = set()
        self.requeue: set[int] = set()
        self.undo: list[dict[str, Any]] = []
        self.touched_schemes: set[int] = set()
        self.priorities = False  # a node's carding priority changed: rescore the waiting items

    def scheme(self, key: str) -> TaxScheme:
        found = self.session.scalars(select(TaxScheme).where(TaxScheme.key == key)).one_or_none()
        if found is None:
            raise ChangeError(f"unknown scheme '{key}'")
        return found

    def node(self, scheme: TaxScheme, key: str, *, active: bool = True) -> TaxNode:
        found = self.session.scalars(
            select(TaxNode).where(TaxNode.scheme_id == scheme.id, TaxNode.key == key)
        ).one_or_none()
        if found is None or (active and found.status != "active"):
            raise ChangeError(f"unknown node '{scheme.key}:{key}'")
        return found

    def items_under(self, node_ids: list[int]) -> set[int]:
        if not node_ids:
            return set()
        rows = self.session.execute(
            text(
                "SELECT DISTINCT l.item_id FROM card_labels l JOIN tax_nodes n ON n.id = l.node_id"
                " WHERE n.path && CAST(:ids AS integer[])"
            ),
            {"ids": node_ids},
        )
        return {int(r[0]) for r in rows}

    def items_with_keys(self, keys: list[str]) -> set[int]:
        if not keys:
            return set()
        rows = self.session.execute(
            text("SELECT item_id FROM item_cards WHERE technology_keys ?| CAST(:keys AS text[])"),
            {"keys": keys},
        )
        return {int(r[0]) for r in rows}

    def items_in_scheme(self, scheme: TaxScheme) -> set[int]:
        rows = self.session.execute(
            text("SELECT DISTINCT item_id FROM card_labels WHERE scheme_id = :s"), {"s": scheme.id}
        )
        return {int(r[0]) for r in rows}


def _aliases(values: list[str]) -> list[str]:
    return list(dict.fromkeys(a for a in (normalize(v) for v in values) if a))


def _llm_level(scheme: TaxScheme, depth: int) -> bool:
    return depth <= (scheme.llm_depth or 10**6)


def _subtree(session: Session, node: TaxNode) -> list[TaxNode]:
    return list(session.scalars(select(TaxNode).where(TaxNode.path.contains([node.id]))))


def _rewrite_columns(
    run: _Run, scheme: TaxScheme, src: str, dst: str | None
) -> list[dict[str, Any]]:
    """Replace `src` by `dst` (None = drop) where the LLM columns hold it; returns old values."""
    session = run.session
    if scheme.key == "technology":
        rows = session.execute(
            text(
                "SELECT item_id, themes, field FROM item_cards WHERE themes ? :src OR field = :src"
            ),
            {"src": src},
        ).all()
        old = [{"item_id": r[0], "themes": r[1], "field": r[2]} for r in rows]
        # one statement: replace or drop the key, keep the order, drop duplicates
        session.execute(
            text(
                "UPDATE item_cards c SET themes = coalesce(("
                " SELECT jsonb_agg(k ORDER BY pos) FROM ("
                "  SELECT k, min(pos) AS pos FROM ("
                "   SELECT CASE WHEN e.value = :src THEN CAST(:dst AS text) ELSE e.value END AS k,"
                "          e.pos"
                "   FROM jsonb_array_elements_text(c.themes) WITH ORDINALITY AS e(value, pos)"
                "  ) a WHERE k IS NOT NULL GROUP BY k) b), '[]'::jsonb),"
                " field = CASE WHEN c.field = :src THEN CAST(:dst AS text) ELSE c.field END"
                " WHERE c.themes ? :src OR c.field = :src"
            ),
            {"src": src, "dst": dst},
        )
    elif scheme.key in LIST_COLUMNS:
        column = LIST_COLUMNS[scheme.key]
        rows = session.execute(
            text(f"SELECT item_id, {column} FROM item_cards WHERE {column} = :src"), {"src": src}
        ).all()
        old = [{"item_id": r[0], column: r[1]} for r in rows]
        session.execute(
            text(f"UPDATE item_cards SET {column} = :dst WHERE {column} = :src"),
            {"src": src, "dst": dst},
        )
    else:
        rows = session.execute(
            text(
                "SELECT item_id, extra_labels FROM item_cards WHERE extra_labels -> :scheme ? :src"
            ),
            {"scheme": scheme.key, "src": src},
        ).all()
        old = [{"item_id": r[0], "extra_labels": r[1]} for r in rows]
        for row in old:
            labels = dict(row["extra_labels"] or {})
            keys = [dst if k == src else k for k in labels.get(scheme.key, [])]
            labels[scheme.key] = [k for k in dict.fromkeys(keys) if k is not None]
            session.execute(
                text("UPDATE item_cards SET extra_labels = CAST(:v AS jsonb) WHERE item_id = :id"),
                {"v": _json(labels), "id": row["item_id"]},
            )
    run.affected.update(int(row["item_id"]) for row in old)
    return old


def _json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


# ---- operation handlers -----------------------------------------------------------------------


def _create_node(run: _Run, op: CreateNode) -> OpOutcome:
    scheme = run.scheme(op.scheme)
    existing = run.session.scalars(
        select(TaxNode).where(TaxNode.scheme_id == scheme.id, TaxNode.key == op.key)
    ).one_or_none()
    if existing is not None:
        raise ChangeError(f"'{op.scheme}:{op.key}' already exists ({existing.status})")
    parent = run.node(scheme, op.parent) if op.parent else None
    if parent is not None and scheme.structure == "list":
        raise ChangeError(f"'{op.scheme}' is a list: nodes have no parent")
    node = TaxNode(
        scheme_id=scheme.id,
        parent_id=parent.id if parent else None,
        key=op.key,
        label=op.label,
        definition=op.definition,
        include_text=op.include_text,
        exclude_text=op.exclude_text,
        aliases=_aliases(op.aliases),
        attrs={},
        sort=op.sort,
        edited_in_console=True,
        path=[],
        depth=(parent.depth + 1) if parent else 1,
    )
    run.session.add(node)
    run.session.flush()
    run.touched_schemes.add(scheme.id)
    run.undo.append(
        {"op": "update_node", "scheme": op.scheme, "key": op.key, "status": "deprecated"}
    )
    hits = run.items_with_keys([node.key, *node.aliases])
    run.affected |= hits
    outcome = OpOutcome(op=op.op, summary=f"'{op.label}' 추가 (깊이 {node.depth})", cards=len(hits))
    if _llm_level(scheme, node.depth):
        scope = run.items_under([parent.id]) if parent else run.items_in_scheme(scheme)
        if op.requeue:
            run.requeue |= scope
            outcome.requeued = len(scope)
        else:
            outcome.warnings.append(
                "LLM이 고르는 깊이입니다. 재분류하지 않으면 새 카드부터 적용됩니다"
                f" (대상 후보 {len(scope)}건)."
            )
    return outcome


def _update_node(run: _Run, op: UpdateNode) -> OpOutcome:
    scheme = run.scheme(op.scheme)
    node = run.node(scheme, op.key, active=False)
    changes = op.model_dump(exclude={"op", "scheme", "key"}, exclude_unset=True)
    if "aliases" in changes:
        changes["aliases"] = _aliases(changes["aliases"])
    if "priority" in changes:
        priority = changes.pop("priority")
        attrs = dict(node.attrs or {})
        run.undo.append(
            {
                "op": "update_node",
                "scheme": op.scheme,
                "key": op.key,
                "priority": attrs.get("priority", 1),
            }
        )
        attrs["priority"] = 1 if priority is None else priority
        node.attrs = attrs
        run.priorities = True
    old = {name: getattr(node, name) for name in changes}
    keys_before = [node.key, *(node.aliases or [])]
    for name, value in changes.items():
        setattr(node, name, value)
    node.edited_in_console = True
    run.session.flush()
    run.undo.append({"op": "update_node", "scheme": op.scheme, "key": op.key, **old})
    if "aliases" in changes or "status" in changes:
        hits = run.items_with_keys(list({*keys_before, *(node.aliases or [])}))
        hits |= run.items_under([node.id])
        run.affected |= hits
    else:
        hits = set()
    return OpOutcome(
        op=op.op, summary=f"'{node.label}' 수정: {', '.join(changes)}", cards=len(hits)
    )


def _move_node(run: _Run, op: MoveNode) -> OpOutcome:
    scheme = run.scheme(op.scheme)
    node = run.node(scheme, op.key)
    if scheme.structure == "list" and op.parent:
        raise ChangeError(f"'{op.scheme}' is a list: nodes have no parent")
    parent = run.node(scheme, op.parent) if op.parent else None
    if parent is not None and node.id in (parent.path or []):
        raise ChangeError(f"'{op.parent}' is inside '{op.key}': a node cannot move under itself")
    old_parent = run.session.get(TaxNode, node.parent_id) if node.parent_id else None
    before = {n.id: n.depth for n in _subtree(run.session, node)}
    node.parent_id = parent.id if parent else None
    run.session.flush()
    rebuild_paths(run.session, scheme.id)
    run.undo.append(
        {
            "op": "move_node",
            "scheme": op.scheme,
            "key": op.key,
            "parent": old_parent.key if old_parent else None,
        }
    )
    hits = run.items_under([node.id])
    run.affected |= hits
    outcome = OpOutcome(
        op=op.op,
        summary=f"'{node.label}' 이동 → {parent.label if parent else '최상위'}",
        cards=len(hits),
    )
    crossed = [
        n
        for n in _subtree(run.session, node)
        if _llm_level(scheme, before.get(n.id, n.depth)) != _llm_level(scheme, n.depth)
    ]
    if crossed:
        if op.requeue:
            run.requeue |= hits
            outcome.requeued = len(hits)
        else:
            outcome.warnings.append(
                f"LLM 깊이 경계를 넘는 노드 {len(crossed)}개: 재분류 전까지 기존 라벨이 유지됩니다."
            )
    return outcome


def _absorb_aliases(target: TaxNode, source: TaxNode) -> list[str]:
    old = list(target.aliases or [])
    target.aliases = list(dict.fromkeys([*old, source.key, *(source.aliases or [])]))
    return old


def _move_children(
    run: _Run, scheme: TaxScheme, source: TaxNode, new_parent: TaxNode | None
) -> None:
    for child in run.session.scalars(select(TaxNode).where(TaxNode.parent_id == source.id)):
        run.undo.append(
            {"op": "move_node", "scheme": scheme.key, "key": child.key, "parent": source.key}
        )
        child.parent_id = new_parent.id if new_parent else None
    run.session.flush()


def _repoint_relations(run: _Run, source: TaxNode, target: TaxNode | None) -> None:
    for relation in run.session.scalars(
        select(TaxRelation).where(
            (TaxRelation.from_node_id == source.id) | (TaxRelation.to_node_id == source.id)
        )
    ):
        if target is None:
            continue
        if relation.from_node_id == source.id:
            relation.from_node_id = target.id
        if relation.to_node_id == source.id:
            relation.to_node_id = target.id
    run.session.flush()


def _merge_node(run: _Run, op: MergeNode) -> OpOutcome:
    scheme = run.scheme(op.scheme)
    source, target = run.node(scheme, op.key), run.node(scheme, op.into)
    if source.id == target.id or source.id in (target.path or []):
        raise ChangeError(f"'{op.into}' is '{op.key}' or inside it")
    if _llm_level(scheme, source.depth) and not _llm_level(scheme, target.depth):
        raise ChangeError("a node the LLM chooses can only merge into another such node")
    hits = run.items_under([source.id])
    _move_children(run, scheme, source, target)
    old_aliases = _absorb_aliases(target, source)
    old_rows = _rewrite_columns(run, scheme, source.key, target.key)
    _repoint_relations(run, source, target)
    source.status, source.merged_into_id = "merged", target.id
    run.session.flush()
    rebuild_paths(run.session, scheme.id)
    run.undo += [
        {"op": "update_node", "scheme": op.scheme, "key": op.into, "aliases": old_aliases},
        {"op": "update_node", "scheme": op.scheme, "key": op.key, "status": "active"},
        {"op": "restore_columns", "rows": old_rows},
    ]
    run.affected |= hits | run.items_under([target.id])
    return OpOutcome(op=op.op, summary=f"'{source.label}' → '{target.label}' 통합", cards=len(hits))


def _retire_node(run: _Run, op: RetireNode) -> OpOutcome:
    scheme = run.scheme(op.scheme)
    source = run.node(scheme, op.key)
    target = run.node(scheme, op.replacement) if op.replacement else None
    if target is not None and (target.id == source.id or source.id in (target.path or [])):
        raise ChangeError(f"'{op.replacement}' is '{op.key}' or inside it")
    hits = run.items_under([source.id])
    parent = run.session.get(TaxNode, source.parent_id) if source.parent_id else None
    _move_children(run, scheme, source, target or parent)
    undo: list[dict[str, Any]] = []
    if target is not None:
        undo.append(
            {
                "op": "update_node",
                "scheme": op.scheme,
                "key": target.key,
                "aliases": _absorb_aliases(target, source),
            }
        )
    old_rows = _rewrite_columns(run, scheme, source.key, target.key if target else None)
    _repoint_relations(run, source, target)
    source.status = "deprecated"
    run.session.flush()
    rebuild_paths(run.session, scheme.id)
    run.undo += [
        *undo,
        {"op": "update_node", "scheme": op.scheme, "key": op.key, "status": "active"},
        {"op": "restore_columns", "rows": old_rows},
    ]
    run.affected |= hits
    where = f"→ '{target.label}'" if target else "(라벨 삭제)"
    return OpOutcome(op=op.op, summary=f"'{source.label}' 폐지 {where}", cards=len(hits))


def _split_node(run: _Run, op: SplitNode) -> OpOutcome:
    scheme = run.scheme(op.scheme)
    source = run.node(scheme, op.key)
    parent = run.session.get(TaxNode, source.parent_id) if source.parent_id else None
    hits = run.items_under([source.id])
    for part in op.parts:
        _create_node(
            run,
            CreateNode(
                op="create_node",
                scheme=op.scheme,
                key=part.key,
                label=part.label,
                parent=parent.key if parent else None,
                definition=part.definition,
                aliases=part.aliases,
            ),
        )
    _move_children(run, scheme, source, parent)
    old_rows = _rewrite_columns(run, scheme, source.key, None)
    source.status = "deprecated"
    run.session.flush()
    rebuild_paths(run.session, scheme.id)
    run.undo += [
        {"op": "update_node", "scheme": op.scheme, "key": op.key, "status": "active"},
        {"op": "restore_columns", "rows": old_rows},
    ]
    outcome = OpOutcome(
        op=op.op,
        summary=f"'{source.label}' → {', '.join(p.label for p in op.parts)} 분할",
        cards=len(hits),
    )
    if _llm_level(scheme, source.depth):
        run.requeue |= hits
        outcome.requeued = len(hits)
    run.affected |= hits
    return outcome


def _create_scheme(run: _Run, op: CreateScheme) -> OpOutcome:
    if (
        op.key in BUILTIN
        or run.session.scalars(select(TaxScheme).where(TaxScheme.key == op.key)).first()
    ):
        raise ChangeError(f"scheme '{op.key}' already exists")
    sort = (run.session.scalar(select(func.max(TaxScheme.sort))) or 0) + 1
    scheme = TaxScheme(
        key=op.key,
        name=op.name,
        structure=op.structure,
        description=op.description,
        min_labels=op.min_labels,
        max_labels=op.max_labels,
        llm_depth=op.llm_depth,
        assign=list(op.assign),
        uses=list(op.uses),
        level_names=list(op.level_names),
        sort=sort,
    )
    run.session.add(scheme)
    run.session.flush()
    run.undo.append({"op": "update_scheme", "key": op.key, "status": "inactive"})
    return OpOutcome(op=op.op, summary=f"체계 '{op.name}' 추가")


def _update_scheme(run: _Run, op: UpdateScheme) -> OpOutcome:
    scheme = run.scheme(op.key)
    changes = op.model_dump(exclude={"op", "key", "requeue"}, exclude_unset=True)
    if op.key in BUILTIN and changes.get("status") == "inactive":
        raise ChangeError(f"'{op.key}' has card columns and cannot be switched off")
    old = {name: getattr(scheme, name) for name in changes}
    for name, value in changes.items():
        setattr(scheme, name, value)
    run.session.flush()
    run.undo.append({"op": "update_scheme", "key": op.key, **old})
    hits = (
        run.items_in_scheme(scheme) if {"llm_depth", "assign", "status"} & set(changes) else set()
    )
    run.affected |= hits
    outcome = OpOutcome(
        op=op.op, summary=f"체계 '{scheme.name}' 수정: {', '.join(changes)}", cards=len(hits)
    )
    if op.requeue and {"llm_depth", "max_labels", "min_labels", "assign"} & set(changes):
        run.requeue |= hits
        outcome.requeued = len(hits)
    return outcome


def _relation(run: _Run, op: Relation) -> OpOutcome:
    source = run.node(run.scheme(op.from_scheme), op.from_key)
    target = run.node(run.scheme(op.to_scheme), op.to_key)
    found = run.session.scalars(
        select(TaxRelation).where(
            TaxRelation.from_node_id == source.id,
            TaxRelation.to_node_id == target.id,
            TaxRelation.kind == op.kind,
        )
    ).one_or_none()
    inverse = "remove_relation" if op.op == "add_relation" else "add_relation"
    if op.op == "add_relation" and found is None:
        run.session.add(TaxRelation(from_node_id=source.id, to_node_id=target.id, kind=op.kind))
    elif op.op == "remove_relation" and found is not None:
        run.session.delete(found)
    run.session.flush()
    run.undo.append({**op.model_dump(), "op": inverse})
    hits = run.items_under([source.id])
    run.affected |= hits
    arrow = "→" if op.op == "add_relation" else "↛"
    return OpOutcome(
        op=op.op, summary=f"'{source.label}' {arrow} '{target.label}'", cards=len(hits)
    )


def _restore_columns(run: _Run, op: RestoreColumns) -> OpOutcome:
    for row in op.rows:
        values = {k: v for k, v in row.items() if k != "item_id"}
        sets = ", ".join(
            f"{k} = CAST(:{k} AS jsonb)" if k in ("themes", "extra_labels") else f"{k} = :{k}"
            for k in values
        )
        params = {
            k: (_json(v) if k in ("themes", "extra_labels") else v) for k, v in values.items()
        }
        run.session.execute(
            text(f"UPDATE item_cards SET {sets} WHERE item_id = :id"),
            {**params, "id": row["item_id"]},
        )
        run.affected.add(int(row["item_id"]))
    return OpOutcome(op=op.op, summary=f"카드 {len(op.rows)}건 컬럼 복원", cards=len(op.rows))


HANDLERS: dict[str, Any] = {
    "create_node": _create_node,
    "update_node": _update_node,
    "move_node": _move_node,
    "merge_node": _merge_node,
    "retire_node": _retire_node,
    "split_node": _split_node,
    "create_scheme": _create_scheme,
    "update_scheme": _update_scheme,
    "add_relation": _relation,
    "remove_relation": _relation,
    "restore_columns": _restore_columns,
}


# ---- apply, preview, rollback -----------------------------------------------------------------


def _classify_rate(session: Session, now: datetime) -> float:
    total = session.scalar(
        select(func.coalesce(func.sum(CardRun.classified), 0)).where(
            CardRun.started_at >= now - timedelta(hours=24)
        )
    )
    return float(total or 0) / 24.0


def _prompt_tokens(session: Session) -> int:
    from news_insight.cards.schemas import CARD_HEAD, _instructions

    prompt = _instructions(taxonomy.load(session), CARD_HEAD)
    return len(prompt) // 2  # Korean-heavy text: about two characters per token


def _run_ops(session: Session, ops: list[Any]) -> tuple[_Run, list[OpOutcome]]:
    run = _Run(session)
    # column rewrites skip the per-card trigger; every affected card is relabelled once below
    session.execute(text("SET LOCAL news.bulk_relabel = 'on'"))
    outcomes: list[OpOutcome] = []
    for op in ops:
        outcomes.append(HANDLERS[op.op](run, op))
    for scheme_id in {*run.touched_schemes, *(s.id for s in session.scalars(select(TaxScheme)))}:
        rebuild_paths(session, scheme_id)
    affected = sorted(run.affected)
    for start in range(0, len(affected), 5000):
        relabel(session, affected[start : start + 5000])
    if run.requeue:
        session.execute(
            text("UPDATE item_cards SET taxonomy_revision = :r WHERE item_id = ANY(:ids)"),
            {"r": REQUEUE, "ids": sorted(run.requeue)},
        )
    if run.priorities:  # the host triage job scores them again on its next runs
        session.execute(text("UPDATE item_triage SET model_id = NULL"))
    session.execute(text("SET LOCAL news.bulk_relabel = 'off'"))
    return run, outcomes


def _result(
    session: Session, run: _Run, outcomes: list[OpOutcome], revision_id: int | None, now: datetime
) -> ChangeResult:
    rate = _classify_rate(session, now)
    tokens = _prompt_tokens(session)
    sample_ids = sorted(run.affected)[-5:]
    samples = [
        {"item_id": item_id, "title": title}
        for item_id, title in session.execute(
            select(ItemCard.item_id, ItemCard.title_ko).where(ItemCard.item_id.in_(sample_ids))
        ).tuples()
    ]
    return ChangeResult(
        revision_id=revision_id,
        outcomes=outcomes,
        affected_cards=len(run.affected),
        requeued_cards=len(run.requeue),
        eta_hours=round(len(run.requeue) / rate, 1) if run.requeue and rate else None,
        prompt_tokens=tokens,
        prompt_over_budget=tokens > PROMPT_TOKEN_BUDGET,
        samples=samples,
    )


def preview(session: Session, changes: ChangeSet, *, now: datetime) -> ChangeResult:
    """What applying would do, measured inside a savepoint that is then rolled back."""
    savepoint = session.begin_nested()
    try:
        run, outcomes = _run_ops(session, list(changes.ops))
        return _result(session, run, outcomes, None, now)
    finally:
        savepoint.rollback()


def apply(session: Session, changes: ChangeSet, *, author: str, now: datetime) -> ChangeResult:
    run, outcomes = _run_ops(session, list(changes.ops))
    revision = TaxRevision(
        author=author,
        note=changes.note,
        status="applied",
        changes=[
            {"ops": [op.model_dump() for op in changes.ops], "undo": list(reversed(run.undo))},
        ],
        snapshot=snapshot(session),
    )
    session.add(revision)
    session.flush()
    taxonomy.invalidate()  # this process reloads at once; others within a minute
    return _result(session, run, outcomes, revision.id, now)


def rollback(session: Session, revision_id: int, *, author: str, now: datetime) -> ChangeResult:
    revision = session.get(TaxRevision, revision_id)
    if revision is None or revision.status != "applied" or not revision.changes:
        raise ChangeError(f"revision {revision_id} cannot be rolled back")
    undo = [step for entry in revision.changes for step in entry.get("undo", [])]
    if not undo:
        raise ChangeError(f"revision {revision_id} has nothing to undo")
    changes = ChangeSet.model_validate({"ops": undo, "note": f"rollback of #{revision_id}"})
    result = apply(session, changes, author=author, now=now)
    revision.status = "rolled_back"
    session.flush()
    return result


def counts(
    session: Session, scheme_key: str, *, days: int | None, now: datetime
) -> dict[int, dict[str, int]]:
    """Cards per node: on the node itself and including its descendants (window by first seen)."""
    window = "JOIN items i ON i.id = l.item_id AND i.first_seen_at >= :since" if days else ""
    rows = session.execute(
        text(
            "SELECT n.id,"
            " count(DISTINCT l.item_id) FILTER (WHERE l.node_id = n.id),"
            " count(DISTINCT l.item_id)"
            " FROM card_labels l"
            " JOIN tax_schemes s ON s.id = l.scheme_id AND s.key = :scheme"
            " JOIN tax_nodes ln ON ln.id = l.node_id"
            " JOIN tax_nodes n ON n.id = ANY(ln.path)"
            f" {window}"
            " GROUP BY n.id"
        ),
        {"scheme": scheme_key, "since": now - timedelta(days=days or 0)},
    )
    return {int(r[0]): {"own": int(r[1]), "total": int(r[2])} for r in rows}
