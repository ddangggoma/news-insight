"""Topic dossier API (plan 16 #4), under the reader key. Every call carries the reader's
session token (X-Session-Token): dossiers are shared by the team and record who changed them."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from news_insight.auth import accounts
from news_insight.auth.models import User
from news_insight.db import get_db
from news_insight.dossiers import service
from news_insight.dossiers.models import Dossier, DossierEvidence, DossierHypothesis
from news_insight.public.auth import require_public_key
from news_insight.public.routes import Now
from news_insight.public.schemas import FeedPage

router = APIRouter(
    prefix="/api/public/dossiers", tags=["dossiers"], dependencies=[Depends(require_public_key)]
)
DB = Annotated[Session, Depends(get_db)]


def reader(db: DB, x_session_token: Annotated[str | None, Header()] = None) -> User:
    user = accounts.check_session(db, token=x_session_token or "", now=datetime.now(UTC))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no session")
    return user


Reader = Annotated[User, Depends(reader)]


def dossier_embedder() -> service.Embed | None:
    from news_insight.taxonomy.embeddings import embedder

    return embedder()


Embedder = Annotated[service.Embed | None, Depends(dossier_embedder)]


def _dossier(db: Session, dossier_id: int) -> Dossier:
    dossier = db.get(Dossier, dossier_id)
    if dossier is None or dossier.status != "active":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such dossier")
    return dossier


def _hypothesis(db: Session, dossier: Dossier, hypothesis_id: int) -> DossierHypothesis:
    hypothesis = db.get(DossierHypothesis, hypothesis_id)
    if hypothesis is None or hypothesis.dossier_id != dossier.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such hypothesis")
    return hypothesis


def _unprocessable(error: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


@router.get("")
def list_dossiers(db: DB, user: Reader, now: Now) -> list[service.DossierSummary]:
    return service.summaries(db, now=now)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_dossier(
    db: DB, user: Reader, now: Now, body: service.DossierIn, embed: Embedder
) -> service.DossierDetail:
    try:
        dossier = service.save(db, body, user=user, embed=embed, now=now)
    except service.DossierError as error:
        raise _unprocessable(error) from None
    db.commit()
    return service.detail(db, dossier, now=now)


@router.get("/{dossier_id}")
def get_dossier(dossier_id: int, db: DB, user: Reader, now: Now) -> service.DossierDetail:
    return service.detail(db, _dossier(db, dossier_id), now=now)


@router.put("/{dossier_id}")
def update_dossier(
    dossier_id: int, db: DB, user: Reader, now: Now, body: service.DossierIn, embed: Embedder
) -> service.DossierDetail:
    dossier = _dossier(db, dossier_id)
    try:
        service.save(db, body, user=user, embed=embed, now=now, dossier=dossier)
    except service.DossierError as error:
        raise _unprocessable(error) from None
    db.commit()
    return service.detail(db, dossier, now=now)


@router.delete("/{dossier_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_dossier(dossier_id: int, db: DB, user: Reader, now: Now) -> None:
    dossier = _dossier(db, dossier_id)
    dossier.status, dossier.updated_by, dossier.updated_at = "archived", user.id, now
    db.commit()


@router.get("/{dossier_id}/items")
def dossier_items(
    dossier_id: int,
    db: DB,
    user: Reader,
    now: Now,
    sort: Literal["recent", "relevance", "coverage"] = "recent",
    page: Annotated[int, Query(ge=1, le=200)] = 1,
    size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> FeedPage:
    return service.items(db, _dossier(db, dossier_id), now=now, sort=sort, page=page, size=size)


class HypothesisIn(BaseModel):
    text: str = Field(min_length=4, max_length=500)


class HypothesisPatch(BaseModel):
    text: str | None = Field(default=None, min_length=4, max_length=500)
    status: Literal["open", "supported", "refuted", "mixed"] | None = None


@router.post("/{dossier_id}/hypotheses", status_code=status.HTTP_201_CREATED)
def add_hypothesis(
    dossier_id: int, db: DB, user: Reader, now: Now, body: HypothesisIn, embed: Embedder
) -> list[service.HypothesisOut]:
    dossier = _dossier(db, dossier_id)
    service.add_hypothesis(db, dossier, body.text, user=user, embed=embed, now=now)
    db.commit()
    return service.hypotheses_of(db, dossier.id)


@router.patch("/{dossier_id}/hypotheses/{hypothesis_id}")
def patch_hypothesis(
    dossier_id: int,
    hypothesis_id: int,
    db: DB,
    user: Reader,
    now: Now,
    body: HypothesisPatch,
    embed: Embedder,
) -> list[service.HypothesisOut]:
    dossier = _dossier(db, dossier_id)
    hypothesis = _hypothesis(db, dossier, hypothesis_id)
    if body.text is not None and body.text.strip() != hypothesis.text:
        hypothesis.text = body.text.strip()
        hypothesis.embedding = service.embed_one(embed, hypothesis.text)
    if body.status is not None:
        hypothesis.status = body.status
    hypothesis.updated_at = now
    dossier.updated_at, dossier.updated_by = now, user.id
    db.commit()
    return service.hypotheses_of(db, dossier.id)


@router.delete("/{dossier_id}/hypotheses/{hypothesis_id}")
def delete_hypothesis(
    dossier_id: int, hypothesis_id: int, db: DB, user: Reader, now: Now
) -> list[service.HypothesisOut]:
    dossier = _dossier(db, dossier_id)
    db.delete(_hypothesis(db, dossier, hypothesis_id))
    dossier.updated_at, dossier.updated_by = now, user.id
    db.commit()
    return service.hypotheses_of(db, dossier.id)


@router.get("/{dossier_id}/hypotheses/{hypothesis_id}/suggestions")
def hypothesis_suggestions(
    dossier_id: int, hypothesis_id: int, db: DB, user: Reader, now: Now, embed: Embedder
) -> list[service.Suggestion]:
    dossier = _dossier(db, dossier_id)
    found = service.suggestions(
        db, dossier, _hypothesis(db, dossier, hypothesis_id), embed=embed, now=now
    )
    db.commit()  # a hypothesis embedded just now keeps its vector
    return found


class EvidenceIn(BaseModel):
    item_id: int
    stance: Literal["support", "oppose", "context"]
    note: str | None = Field(default=None, max_length=500)


@router.post("/{dossier_id}/hypotheses/{hypothesis_id}/evidence")
def add_evidence(
    dossier_id: int, hypothesis_id: int, db: DB, user: Reader, now: Now, body: EvidenceIn
) -> list[service.HypothesisOut]:
    from sqlalchemy.dialects.postgresql import insert

    from news_insight.content.models import Item

    dossier = _dossier(db, dossier_id)
    hypothesis = _hypothesis(db, dossier, hypothesis_id)
    if db.get(Item, body.item_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such item")
    note = (body.note or "").strip() or None
    db.execute(
        insert(DossierEvidence)
        .values(
            hypothesis_id=hypothesis.id,
            item_id=body.item_id,
            stance=body.stance,
            note=note,
            added_by=user.id,
            created_at=now,
        )
        .on_conflict_do_update(
            constraint="uq_dossier_evidence_pair",
            set_={"stance": body.stance, "note": note, "added_by": user.id},
        )
    )
    dossier.updated_at, dossier.updated_by = now, user.id
    db.commit()
    return service.hypotheses_of(db, dossier.id)


@router.delete("/{dossier_id}/evidence/{evidence_id}")
def delete_evidence(
    dossier_id: int, evidence_id: int, db: DB, user: Reader, now: Now
) -> list[service.HypothesisOut]:
    dossier = _dossier(db, dossier_id)
    evidence = db.get(DossierEvidence, evidence_id)
    hypothesis = db.get(DossierHypothesis, evidence.hypothesis_id) if evidence else None
    if evidence is None or hypothesis is None or hypothesis.dossier_id != dossier.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such evidence")
    db.delete(evidence)
    dossier.updated_at, dossier.updated_by = now, user.id
    db.commit()
    return service.hypotheses_of(db, dossier.id)
