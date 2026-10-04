"""Regenerate apps/web/lib/taxonomy.ts from taxonomy/catalog.py (drift is tested).

Usage: uv run python scripts/gen_taxonomy_ts.py
"""

import json
from pathlib import Path

from news_insight.taxonomy.catalog import (
    FIELDS,
    IMPACTS,
    SCOPES,
    SIGNAL_TYPES,
    TAXONOMY_REVISED_ON,
    TAXONOMY_REVISION,
    Node,
)

TARGET = Path(__file__).resolve().parents[2] / "web" / "lib" / "taxonomy.ts"


def block(name: str, nodes: list[Node]) -> str:
    body = json.dumps({n.key: n.name for n in nodes}, ensure_ascii=False, indent=2)
    return f"export const {name}: Record<string, string> = {body};\n"


themes = [theme for field in FIELDS for theme in field.themes]
TARGET.write_text(
    "// Generated from apps/api/src/news_insight/taxonomy/catalog.py by\n"
    "// apps/api/scripts/gen_taxonomy_ts.py — do not edit by hand.\n"
    f'export const TAXONOMY_REVISION = "{TAXONOMY_REVISION}";\n'
    f'export const TAXONOMY_REVISED_ON = "{TAXONOMY_REVISED_ON}";\n\n'
    + "\n".join(
        [
            block("FIELD_LABEL", list(FIELDS)),
            block("THEME_LABEL", themes),
            block("SIGNAL_LABEL", list(SIGNAL_TYPES)),
            block("IMPACT_LABEL", list(IMPACTS)),
            block("SCOPE_LABEL", list(SCOPES)),
        ]
    ),
    encoding="utf-8",
)
print(f"wrote {TARGET}")
