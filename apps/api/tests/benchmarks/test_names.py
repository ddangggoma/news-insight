import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from news_insight.benchmarks.models import AiModel, AiModelAlias
from news_insight.benchmarks.names import normalize, resolve_model


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Claude Opus 5.5", "claude-opus-5-5"),
        ("claude-opus-5.5", "claude-opus-5-5"),
        ("Gemini 4 Carbon (High)", "gemini-4-carbon"),
        ("gpt-5-5-2026-06-01", "gpt-5-5"),
        ("  GPT_6  Astra ", "gpt-6-astra"),
        ("claude-sonnet-5-20261015", "claude-sonnet-5"),
        ("Model--X  (thinking) ", "model-x"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


@pytest.mark.db
def test_resolve_by_alias_then_normalized(db_session: Session) -> None:
    opus = AiModel(name="claude-opus-5-5", org="Anthropic")
    carbon = AiModel(name="gemini-4-carbon", org="Google")
    db_session.add_all([opus, carbon])
    db_session.flush()
    db_session.add(AiModelAlias(alias="Opus 5.5 (Thinking 16k)", model_id=carbon.id))
    db_session.flush()

    # An alias hit wins over the normalized-name lookup, even where the name would also match
    assert resolve_model(db_session, "Opus 5.5 (Thinking 16k)", "Anthropic") == carbon.id
    # No alias: the normalized spelling is looked up in the model names
    assert resolve_model(db_session, "Claude Opus 5.5", "Anthropic") == opus.id
    assert resolve_model(db_session, "claude-opus-5.5-20261001", None) == opus.id
    # A normalized spelling can also hit an alias stored in normalized form
    db_session.add(AiModelAlias(alias="gem-4", model_id=carbon.id))
    db_session.flush()
    assert resolve_model(db_session, "Gem 4", None) == carbon.id


@pytest.mark.db
def test_unknown_returns_none(db_session: Session) -> None:
    before = db_session.scalar(select(func.count()).select_from(AiModel))
    assert resolve_model(db_session, "Totally New Model 9", "Nobody") is None
    assert db_session.scalar(select(func.count()).select_from(AiModel)) == before
    assert db_session.scalar(select(func.count()).select_from(AiModelAlias)) == 0
