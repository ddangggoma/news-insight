"""Import every ORM module here so Alembic sees the complete metadata."""

import news_insight.auth.models  # noqa: F401
import news_insight.briefing.models  # noqa: F401
import news_insight.cards.models  # noqa: F401
import news_insight.collect.models  # noqa: F401
import news_insight.content.models  # noqa: F401
import news_insight.digest.models  # noqa: F401
import news_insight.ops.models  # noqa: F401
import news_insight.review.models  # noqa: F401
import news_insight.signals.models  # noqa: F401
import news_insight.sources.models  # noqa: F401
import news_insight.stories.models  # noqa: F401
import news_insight.strategy.models  # noqa: F401
import news_insight.technologies.models  # noqa: F401
