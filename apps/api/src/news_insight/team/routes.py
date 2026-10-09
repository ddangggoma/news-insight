"""Team collaboration API (plan 16 #12): comments on cards (their memos), collections and
dossiers, and shared collections of cards. Under the reader key with the reader's session;
everything is visible to every signed-in user, and only the author or an admin removes a
comment."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from news_insight.auth.models import Role, User
from news_insight.cards.models import ItemCard
from news_insight.content.models import Item
from news_insight.db import get_db
from news_insight.dossiers.models import Dossier
from news_insight.dossiers.routes import Reader
from news_insight.public.auth import require_public_key
from news_insight.public.feed import _published, _reader_item, company_refs
from news_insight.public.schemas import ReaderItem
from news_insight.team.models import Collection, CollectionItem, Comment

router = APIRouter(
    prefix="/api/public/team", tags=["team"], dependencies=[Depends(require_public_key)]
)
DB = Annotated[Session, Depends(get_db)]
Kind = Literal["item", "collection", "dossier"]


def _now() -> datetime:
    return datetime.now(UTC)


class CommentIn(BaseModel):
    kind: Kind
    target_id: int
    body: str = Field(min_length=1, max_length=2000)


class CommentOut(BaseModel):
    id: int
    body: str
    author: str | None
    created_at: datetime
    mine: bool


def _target_exists(db: Session, kind: str, target_id: int) -> bool:
    model = {"item": Item, "collection": Collection, "dossier": Dossier}[kind]
    return db.get(model, target_id) is not None


def _comments(db: Session, kind: str, target_id: int, user: User) -> list[CommentOut]:
    rows = db.execute(
        select(Comment, User.name)
        .outerjoin(User, User.id == Comment.user_id)
        .where(
            Comment.target_kind == kind,
            Comment.target_id == target_id,
            Comment.deleted_at.is_(None),
        )
        .order_by(Comment.created_at)
    ).tuples()
    return [
        CommentOut(
            id=c.id, body=c.body, author=name, created_at=c.created_at, mine=c.user_id == user.id
        )
        for c, name in rows
    ]


@router.get("/comments")
def list_comments(
    db: DB, user: Reader, kind: Kind, target_id: Annotated[int, Query(ge=1)]
) -> list[CommentOut]:
    return _comments(db, kind, target_id, user)


@router.post("/comments", status_code=status.HTTP_201_CREATED)
def add_comment(db: DB, user: Reader, body: CommentIn) -> list[CommentOut]:
    if not _target_exists(db, body.kind, body.target_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no such {body.kind}")
    db.add(
        Comment(
            target_kind=body.kind,
            target_id=body.target_id,
            user_id=user.id,
            body=body.body.strip(),
            created_at=_now(),
        )
    )
    db.commit()
    return _comments(db, body.kind, body.target_id, user)


@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, db: DB, user: Reader) -> list[CommentOut]:
    comment = db.get(Comment, comment_id)
    if comment is None or comment.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such comment")
    if comment.user_id != user.id and user.role != Role.ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "only the author or an admin removes a comment"
        )
    comment.deleted_at = _now()
    db.commit()
    return _comments(db, comment.target_kind, comment.target_id, user)


class CollectionIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class CollectionSummary(BaseModel):
    id: int
    title: str
    description: str | None
    items: int
    comments: int
    created_by: str | None
    updated_at: datetime


class CollectionEntry(BaseModel):
    item: ReaderItem
    note: str | None
    added_by: str | None
    added_at: datetime


class CollectionDetail(CollectionSummary):
    entries: list[CollectionEntry]


def _summaries(db: Session, ids: list[int] | None = None) -> list[CollectionSummary]:
    counts = (
        select(CollectionItem.collection_id, func.count().label("n"))
        .group_by(CollectionItem.collection_id)
        .subquery()
    )
    notes = (
        select(Comment.target_id, func.count().label("n"))
        .where(Comment.target_kind == "collection", Comment.deleted_at.is_(None))
        .group_by(Comment.target_id)
        .subquery()
    )
    query = (
        select(Collection, func.coalesce(counts.c.n, 0), func.coalesce(notes.c.n, 0), User.name)
        .outerjoin(counts, counts.c.collection_id == Collection.id)
        .outerjoin(notes, notes.c.target_id == Collection.id)
        .outerjoin(User, User.id == Collection.created_by)
        .where(Collection.status == "active")
        .order_by(Collection.updated_at.desc())
    )
    if ids is not None:
        query = query.where(Collection.id.in_(ids))
    return [
        CollectionSummary(
            id=c.id,
            title=c.title,
            description=c.description,
            items=n,
            comments=k,
            created_by=name,
            updated_at=c.updated_at,
        )
        for c, n, k, name in db.execute(query).tuples()
    ]


def _collection(db: Session, collection_id: int) -> Collection:
    found = db.get(Collection, collection_id)
    if found is None or found.status != "active":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such collection")
    return found


def _detail(db: Session, collection: Collection) -> CollectionDetail:
    [summary] = _summaries(db, [collection.id])
    rows = (
        db.execute(
            select(CollectionItem, User.name)
            .outerjoin(User, User.id == CollectionItem.added_by)
            .where(CollectionItem.collection_id == collection.id)
            .order_by(CollectionItem.added_at.desc())
        )
        .tuples()
        .all()
    )
    published = {
        item.id: (item, source, card)
        for item, source, card in _published(db, [e.item_id for e, _ in rows])
    }
    names = company_refs(db, [card for _, _, card in published.values()])
    entries = [
        CollectionEntry(
            item=_reader_item(*published[e.item_id], None, {}, names),
            note=e.note,
            added_by=name,
            added_at=e.added_at,
        )
        for e, name in rows
        if e.item_id in published
    ]
    return CollectionDetail(**summary.model_dump(), entries=entries)


@router.get("/collections")
def list_collections(db: DB, user: Reader) -> list[CollectionSummary]:
    return _summaries(db)


@router.post("/collections", status_code=status.HTTP_201_CREATED)
def create_collection(db: DB, user: Reader, body: CollectionIn) -> CollectionDetail:
    now = _now()
    collection = Collection(
        title=body.title.strip(),
        description=(body.description or "").strip() or None,
        status="active",
        created_by=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(collection)
    db.commit()
    return _detail(db, collection)


@router.get("/collections/{collection_id}")
def get_collection(collection_id: int, db: DB, user: Reader) -> CollectionDetail:
    return _detail(db, _collection(db, collection_id))


@router.put("/collections/{collection_id}")
def update_collection(
    collection_id: int, db: DB, user: Reader, body: CollectionIn
) -> CollectionDetail:
    collection = _collection(db, collection_id)
    collection.title = body.title.strip()
    collection.description = (body.description or "").strip() or None
    collection.updated_at = _now()
    db.commit()
    return _detail(db, collection)


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_collection(collection_id: int, db: DB, user: Reader) -> None:
    collection = _collection(db, collection_id)
    collection.status, collection.updated_at = "archived", _now()
    db.commit()


class EntryIn(BaseModel):
    item_id: int
    note: str | None = Field(default=None, max_length=500)


@router.post("/collections/{collection_id}/items")
def add_entry(collection_id: int, db: DB, user: Reader, body: EntryIn) -> CollectionDetail:
    collection = _collection(db, collection_id)
    if db.scalar(select(ItemCard.id).where(ItemCard.item_id == body.item_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such card")
    now = _now()
    note = (body.note or "").strip() or None
    db.execute(
        insert(CollectionItem)
        .values(
            collection_id=collection.id,
            item_id=body.item_id,
            note=note,
            added_by=user.id,
            added_at=now,
        )
        .on_conflict_do_update(index_elements=["collection_id", "item_id"], set_={"note": note})
    )
    collection.updated_at = now
    db.commit()
    return _detail(db, collection)


@router.delete("/collections/{collection_id}/items/{item_id}")
def remove_entry(collection_id: int, item_id: int, db: DB, user: Reader) -> CollectionDetail:
    collection = _collection(db, collection_id)
    entry = db.get(CollectionItem, (collection.id, item_id))
    if entry is not None:
        db.delete(entry)
        collection.updated_at = _now()
        db.commit()
    return _detail(db, collection)


class ItemTeam(BaseModel):
    comments: list[CommentOut]
    collections: list[CollectionSummary]  # the collections that hold this card
    all_collections: list[CollectionSummary]


@router.get("/items/{item_id}")
def item_team(item_id: int, db: DB, user: Reader) -> ItemTeam:
    holding = list(
        db.scalars(select(CollectionItem.collection_id).where(CollectionItem.item_id == item_id))
    )
    every = _summaries(db)
    return ItemTeam(
        comments=_comments(db, "item", item_id, user),
        collections=[c for c in every if c.id in holding],
        all_collections=every,
    )
