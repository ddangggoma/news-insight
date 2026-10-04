"""Generate, store and read daily digests."""

import hashlib
import json
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.console.schemas import Page
from news_insight.content.models import Item
from news_insight.digest.bundle import build_bundle, digest_window
from news_insight.digest.claude import ClaudeClient, ClaudeError
from news_insight.digest.models import Digest, DigestStatus
from news_insight.digest.schemas import (
    DigestContent,
    DigestItemRef,
    DigestOut,
    DigestSummary,
    fallback_content,
    inline_schema,
    validate_content,
)
from news_insight.sources.models import Source

DIGEST_SCHEMA = inline_schema(DigestContent)


def generate_digest(
    session: Session, *, digest_date: date, now: datetime, client: ClaudeClient, model: str
) -> Digest:
    start, end = digest_window(digest_date)
    bundle = build_bundle(session, start=start, end=end)
    input_hash = hashlib.sha256(
        json.dumps(bundle.payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    existing = session.scalars(
        select(Digest).where(
            Digest.digest_date == digest_date,
            Digest.input_hash == input_hash,
            Digest.status == DigestStatus.PUBLISHED,
        )
    ).first()
    if existing is not None:
        return existing
    version = (
        session.scalar(select(func.max(Digest.version)).where(Digest.digest_date == digest_date))
        or 0
    ) + 1
    status, error, cost, model_name = DigestStatus.FALLBACK, None, None, None
    content: DigestContent
    if bundle.item_count == 0:
        content, error = fallback_content(bundle, reason="no items"), "no items in window"
    else:
        try:
            result = client.generate(bundle.payload, schema=DIGEST_SCHEMA, model=model)
            validated = validate_content(result.structured, known_ids=bundle.item_ids)
            if validated is None:
                raise ClaudeError("structured output failed evidence validation")
            content, status = validated, DigestStatus.PUBLISHED
            cost, model_name = result.cost_usd, result.model
        except ClaudeError as exc:
            content, error = fallback_content(bundle, reason=str(exc)), str(exc)
    digest = Digest(
        digest_date=digest_date,
        version=version,
        status=status,
        model=model_name,
        generated_at=now,
        window_start=start,
        window_end=end,
        item_count=bundle.item_count,
        input_hash=input_hash,
        content=content.model_dump(mode="json"),
        cost_usd=cost,
        error=error,
    )
    session.add(digest)
    session.flush()
    return digest


def _referenced_ids(content: DigestContent) -> set[int]:
    ids = {i for insight in content.insights for i in insight.item_ids}
    for track in content.tracks:
        for category in track.categories:
            for point in category.points:
                ids.update(point.item_ids)
    return ids


def digest_out(session: Session, digest: Digest) -> DigestOut:
    content = DigestContent.model_validate(digest.content)
    ids = _referenced_ids(content)
    refs = [
        DigestItemRef(
            id=item.id, title=item.title, url=item.url, source_name=source.name, track=item.track
        )
        for item, source in session.execute(
            select(Item, Source).join(Source, Source.id == Item.source_id).where(Item.id.in_(ids))
        ).tuples()
    ]
    return DigestOut(
        digest_date=digest.digest_date,
        version=digest.version,
        status=digest.status,
        model=digest.model,
        generated_at=digest.generated_at,
        window_start=digest.window_start,
        window_end=digest.window_end,
        item_count=digest.item_count,
        cost_usd=digest.cost_usd,
        error=digest.error,
        content=content,
        items=sorted(refs, key=lambda ref: ref.id),
    )


def latest_digest(session: Session) -> Digest | None:
    return session.scalars(
        select(Digest).order_by(Digest.digest_date.desc(), Digest.version.desc()).limit(1)
    ).first()


def digest_for(session: Session, digest_date: date) -> Digest | None:
    return session.scalars(
        select(Digest)
        .where(Digest.digest_date == digest_date)
        .order_by(Digest.version.desc())
        .limit(1)
    ).first()


def list_digests(session: Session, *, page: int, size: int) -> Page[DigestSummary]:
    total = session.scalar(select(func.count()).select_from(Digest)) or 0
    digests = session.scalars(
        select(Digest)
        .order_by(Digest.digest_date.desc(), Digest.version.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return Page[DigestSummary](
        items=[
            DigestSummary(
                digest_date=digest.digest_date,
                version=digest.version,
                status=digest.status,
                headline=str(digest.content.get("headline", "")),
                item_count=digest.item_count,
                generated_at=digest.generated_at,
            )
            for digest in digests
        ],
        total=total,
        page=page,
        size=size,
    )
