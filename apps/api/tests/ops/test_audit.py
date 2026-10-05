import pytest
from sqlalchemy.orm import Session

from news_insight.ops.audit import render, run_audit
from tests.public.seed import seed_corpus

pytestmark = pytest.mark.db


def test_audit_runs_every_check_and_renders(db_session: Session) -> None:
    seed_corpus(db_session)
    sections = run_audit(db_session, with_containers=False)

    assert [s.title for s in sections] == [
        "수집",
        "중복 수집",
        "카드·번역",
        "분류",
        "이슈 묶기",
        "DB 성능",
    ]
    text = render(sections)
    assert text.startswith("# 운영 점검") and "## 발견 사항" in text
    assert "### 카드 상태" in text and "### 테이블 크기 상위" in text
