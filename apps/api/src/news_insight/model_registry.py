"""Import every ORM module here so Alembic sees the complete metadata."""

import news_insight.collect.models  # noqa: F401
import news_insight.content.models  # noqa: F401
import news_insight.digest.models  # noqa: F401
import news_insight.sources.models  # noqa: F401
