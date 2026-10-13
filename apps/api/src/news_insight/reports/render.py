"""Trend report output (plan 17 R1): the writer's answer checked against the evidence, then
rendered as one self-contained HTML page (no scripts, inline styles, light and dark, print) and
as the export document model, so Markdown, Word and PowerPoint come for free."""

from collections.abc import Iterable
from datetime import datetime
from html import escape
from typing import Any

from news_insight.export.document import Block, Doc, Section, Source
from news_insight.public.periods import KST
from news_insight.reports.prompts import CONFIDENCE, IMPACT, LIKELIHOOD, MODES, TRAJECTORY
from news_insight.taxonomy.catalog import SIGNAL_TYPES

CONFIDENCE_KO = {"high": "높음", "medium": "보통", "low": "낮음"}
TRAJECTORY_KO = {
    "emerging": "태동",
    "accelerating": "가속",
    "steady": "유지",
    "slowing": "둔화",
    "reversing": "반전",
    "unclear": "불분명",
}
MODE_KO = {
    "asserted": "발생",
    "planned": "계획·예고",
    "expected": "전망",
    "rumored": "소문",
    "negated": "부인",
}
IMPACT_KO = {"opportunity": "기회", "risk": "위험", "watch": "관찰"}
KIND_KO = {
    "company": "기업",
    "person": "인물",
    "institute": "연구기관",
    "government": "정부·규제",
    "startup": "스타트업",
    "other": "기타",
}
RELATION_KO = {
    "self": "삼성",
    "competitor": "경쟁",
    "supplier": "공급",
    "partner": "협력",
    "peer": "주요",
}
REGION_KO = {
    "kr": "국내",
    "global_en": "영미권",
    "jp": "일본",
    "greater_china": "중화권",
    "eu_other": "유럽·기타",
}
TRACK_KO = {
    "news": "뉴스",
    "community": "커뮤니티",
    "research_ip": "연구·특허",
    "oss": "오픈소스",
}
SIGNAL_KO = {node.key: node.name for node in SIGNAL_TYPES}
ID_FIELDS = ("item_ids", "support_ids", "counter_ids")


# --- validation -----------------------------------------------------------------------------


def _clean(value: Any, known: set[int]) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, inner in value.items():
            if key in ID_FIELDS:
                ids = (
                    [i for i in inner if isinstance(i, int) and i in known]
                    if isinstance(inner, list)
                    else []
                )
                out[key] = list(dict.fromkeys(ids))
            else:
                out[key] = _clean(inner, known)
        if out.get("basis") == "evidence" and not out.get("item_ids"):
            out["basis"] = "background"  # cited nothing we gave it: the model's own knowledge
        return out
    if isinstance(value, list):
        return [_clean(inner, known) for inner in value]
    if isinstance(value, str):
        return " ".join(value.split())
    return value


def validate(structured: dict[str, Any], known: Iterable[int]) -> dict[str, Any]:
    """Keep only citations of cards the writer was given, and fill missing sections."""
    content: dict[str, Any] = _clean(structured, set(known))
    for key in (
        "key_points",
        "events",
        "actor_paths",
        "actors",
        "landscape",
        "precedents",
        "implications",
        "assumptions",
        "hypotheses",
        "signposts",
        "gaps",
    ):
        if not isinstance(content.get(key), list):
            content[key] = []
    bottom = content.get("bottom_line")
    if not isinstance(bottom, dict) or not str(bottom.get("judgement") or "").strip():
        raise ValueError("the report has no bottom line")
    if bottom.get("confidence") not in CONFIDENCE:
        bottom["confidence"] = "low"
    trajectory = content.get("trajectory")
    if not isinstance(trajectory, dict):
        content["trajectory"] = {"direction": "unclear", "points": []}
    elif trajectory.get("direction") not in TRAJECTORY:
        trajectory["direction"] = "unclear"
    for event in content["events"]:
        if event.get("mode") not in MODES:
            event["mode"] = "asserted"
    for row in content["implications"]:
        if row.get("impact") not in IMPACT:
            row["impact"] = "watch"
    for row in content["signposts"]:
        if row.get("likelihood") not in LIKELIHOOD:
            row["likelihood"] = "반반"
    content["title"] = str(content.get("title") or "").strip()[:120]
    content["events"].sort(key=lambda e: str(e.get("date") or ""))
    return content


# --- HTML -----------------------------------------------------------------------------------


class Citer:
    """Numbers cards in order of first citation."""

    def __init__(self, sources: dict[str, dict[str, Any]]) -> None:
        self.sources = sources
        self.order: dict[int, int] = {}

    def marks(self, ids: Iterable[int] | None) -> str:
        out = []
        for item_id in ids or []:
            if str(item_id) not in self.sources:
                continue
            number = self.order.setdefault(item_id, len(self.order) + 1)
            out.append(f'<a class="cite" href="#ref-{number}">[{number}]</a>')
        return "".join(out)


def _e(value: Any) -> str:
    return escape(str(value or ""))


def _claim(item: dict[str, Any], citer: Citer, key: str = "text") -> str:
    return f"{_e(item.get(key))} {citer.marks(item.get('item_ids'))}".rstrip()


def _basis(item: dict[str, Any]) -> str:
    if item.get("basis") == "background":
        return (
            ' <span class="tag bg" title="수집 데이터가 아닌 모델 배경지식입니다">'
            "배경지식·검증 필요</span>"
        )
    return ""


def _bars(rows: list[tuple[str, int]], *, width: int = 640, height: int = 140) -> str:
    """Inline SVG column chart (weekly stories)."""
    if not rows:
        return '<p class="muted">주별 자료가 없습니다.</p>'
    top = max(count for _, count in rows) or 1
    gap = 6
    bar = min(max((width - gap * (len(rows) - 1)) / len(rows), 4), 56)  # few weeks: narrow
    parts = []
    for index, (label, count) in enumerate(rows):
        h = round((height - 28) * count / top, 1)
        x = round(index * (bar + gap), 1)
        y = round(height - 18 - h, 1)
        parts.append(
            f'<rect x="{x}" y="{y}" width="{round(bar, 1)}" height="{h}" rx="2" class="bar">'
            f"<title>{_e(label)} 주: {count}건</title></rect>"
            f'<text x="{round(x + bar / 2, 1)}" y="{y - 3}" class="val">{count}</text>'
            f'<text x="{round(x + bar / 2, 1)}" y="{height - 4}" class="axis">'
            f"{_e(label[5:])}</text>"
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="주별 이슈 수" class="chart">'
        + "".join(parts)
        + "</svg>"
    )


def _table(head: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header = "".join(f"<th>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return (
        f'<div class="scroll"><table><thead><tr>{header}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def _list(items: list[str], cls: str = "") -> str:
    if not items:
        return ""
    return f'<ul class="{cls}">' + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


CSS = """
:root{--bg:#fbfbfa;--fg:#1c1d1f;--muted:#62666d;--line:#e3e4e6;--card:#ffffff;--accent:#2f5fd0;
--accent-soft:#e8eefb;--opp:#1f7a4d;--risk:#b4372f;--watch:#8a6a00;--bar:#5b7fd6;}
@media (prefers-color-scheme:dark){:root{--bg:#141517;--fg:#e8e9eb;--muted:#a0a4ab;--line:#2c2e33;
--card:#1b1c1f;--accent:#8fb0ff;--accent-soft:#1f2a44;--opp:#5fc795;--risk:#f08a80;--watch:#e3c35a;
--bar:#7f9fe8;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.7 -apple-system,BlinkMacSystemFont,
"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",sans-serif;word-break:keep-all}
main{max-width:920px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:26px;line-height:1.35;margin:0 0 6px}
h2{font-size:19px;margin:40px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h3{font-size:16px;margin:20px 0 6px}
p{margin:6px 0}
.muted{color:var(--muted)}.meta{color:var(--muted);font-size:13px}
.bluf{background:var(--accent-soft);border-left:4px solid var(--accent);padding:16px 18px;
border-radius:6px;margin:22px 0}
.bluf .label{font-size:12px;font-weight:700;color:var(--accent);letter-spacing:.04em}
.bluf p.j{font-size:17px;font-weight:600;margin:4px 0 8px}
.tag{display:inline-block;font-size:12px;padding:1px 7px;border-radius:999px;
border:1px solid var(--line);
color:var(--muted);white-space:nowrap;vertical-align:1px}
.tag.bg{border-style:dashed}
.tag.opportunity{color:var(--opp);border-color:var(--opp)}.tag.risk{color:var(--risk);border-color:var(--risk)}
.tag.watch{color:var(--watch);border-color:var(--watch)}
.cite{font-size:11px;color:var(--accent);text-decoration:none;vertical-align:super;margin-left:1px}
ul{padding-left:20px;margin:6px 0}li{margin:4px 0}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0}
th,td{border-bottom:1px solid var(--line);padding:7px 8px;text-align:left;vertical-align:top}
th{font-size:12px;color:var(--muted);font-weight:600}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:14px 16px;margin:10px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}
.chart{width:100%;height:auto;margin:6px 0}.chart .bar{fill:var(--bar)}
.chart text{font-size:10px;fill:var(--muted);text-anchor:middle}
.refs{font-size:13px}.refs li{margin:3px 0}.refs a{color:var(--fg)}
.note{font-size:13px;color:var(--muted)}
@media print{body{background:#fff;color:#000}.bluf{break-inside:avoid}h2{break-after:avoid}
.card{break-inside:avoid}}
"""


def _date(moment: str | None) -> str:
    if not moment:
        return ""
    try:
        return datetime.fromisoformat(moment).astimezone(KST).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return moment


def html(report: dict[str, Any]) -> str:
    """The whole page. `report` carries topic, brief, period, content, sources, stats, plan."""
    content: dict[str, Any] = report["content"]
    sources: dict[str, dict[str, Any]] = report["sources"]
    stats: dict[str, Any] = report.get("stats") or {}
    plan: dict[str, Any] = report.get("plan") or {}
    citer = Citer(sources)
    out: list[str] = []
    title = content.get("title") or report["topic"]
    out.append(f"<h1>{_e(title)}</h1>")
    out.append(
        f'<p class="meta">주제: {_e(report["topic"])} · 근거 기간 {_e(report["period_from"])}'
        f" ~ {_e(report['period_to'])} · 이슈 {stats.get('stories', 0)}건 중 근거"
        f" {len(sources)}건 · 작성 {_e(_date(report.get('generated_at')))}"
        f" · {_e(report.get('model') or '')}</p>"
    )
    if report.get("brief"):
        out.append(f'<p class="note">요청 설명: {_e(report["brief"])}</p>')

    bottom = content["bottom_line"]
    out.append(
        '<section class="bluf"><div class="label">핵심 판단</div>'
        f'<p class="j">{_e(bottom.get("judgement"))} {citer.marks(bottom.get("item_ids"))}</p>'
        f'<p class="meta">확신도 <strong>{CONFIDENCE_KO[bottom["confidence"]]}</strong>'
        f" — {_e(bottom.get('confidence_reason'))}</p></section>"
    )
    out.append(_list([_claim(p, citer) for p in content["key_points"]]))

    # 1. timeline axis
    trajectory = content["trajectory"]
    out.append("<h2>1. 흐름 — 시계열</h2>")
    out.append(f'<p>방향: <span class="tag">{TRAJECTORY_KO[trajectory["direction"]]}</span></p>')
    out.append(_bars([(w["week"], int(w["stories"])) for w in stats.get("weekly", [])]))
    out.append('<p class="note">주별 이슈 수(같은 사건 보도는 한 건). 주 시작일(월) 기준.</p>')
    out.append(_list([_claim(p, citer) for p in trajectory.get("points") or []]))
    if content["events"]:
        out.append("<h3>핵심 사건</h3>")
        out.append(
            _table(
                ["날짜", "주체", "행위", "대상", "양태", "내용"],
                [
                    [
                        _e(ev.get("date")),
                        _e(ev.get("actor")),
                        _e(ev.get("action")),
                        _e(ev.get("object")),
                        f'<span class="tag">{MODE_KO[ev["mode"]]}</span>',
                        _claim(ev, citer, "summary"),
                    ]
                    for ev in content["events"]
                ],
            )
        )

    # 2. actor paths
    if content["actor_paths"]:
        out.append("<h2>2. 핵심 주체의 궤적 — 과거와 다음 행보</h2>")
        cards = []
        for path in content["actor_paths"]:
            past = _list([_claim(p, citer) + _basis(p) for p in path.get("past") or []])
            cards.append(
                f'<div class="card"><h3>{_e(path.get("actor"))}</h3>{past}'
                f"<p><strong>읽기</strong> {_e(path.get('reading'))}"
                f" {citer.marks(path.get('item_ids'))}</p>"
                f"<p><strong>다음 행보</strong> {_e(path.get('next'))}</p></div>"
            )
        out.append("".join(cards))

    # 3. landscape axis
    out.append("<h2>3. 주체 지형 — 같은 대상을 두고 누가 무엇을 하나</h2>")
    out.append(_list([_claim(p, citer) for p in content["landscape"]]))
    if content["actors"]:
        out.append(
            _table(
                ["주체", "구분", "위치·전략", "최근 움직임"],
                [
                    [
                        _e(a.get("name")),
                        KIND_KO.get(str(a.get("kind")), "기타"),
                        _e(a.get("position")),
                        f"{_e(a.get('recent'))} {citer.marks(a.get('item_ids'))}",
                    ]
                    for a in content["actors"]
                ],
            )
        )
    if stats.get("companies"):
        out.append("<h3>등록 기업별 보도(자동 집계)</h3>")
        out.append(
            _table(
                [
                    "기업",
                    "관계",
                    "이슈",
                    f"최근({_e(stats.get('recent_since'))}~)",
                    "첫 등장",
                    "마지막",
                ],
                [
                    [
                        _e(c["name"]),
                        RELATION_KO.get(c["relation"], c["relation"]),
                        f'<span class="num">{c["stories"]}</span>',
                        f'<span class="num">{c["recent"]}</span>',
                        _e(c["first_seen"]),
                        _e(c["last_seen"]),
                    ]
                    for c in stats["companies"]
                ],
            )
        )
    mix = stats.get("signal_mix") or []
    if mix:
        out.append("<h3>소식 유형 구성 변화(자동 집계)</h3>")
        out.append(
            _table(
                ["유형", f"최근({_e(stats.get('recent_since'))}~)", "이전"],
                [
                    [
                        SIGNAL_KO.get(m["signal"], _e(m["signal"])),
                        str(m["recent"]),
                        str(m["before"]),
                    ]
                    for m in mix
                ],
            )
        )
    regions = stats.get("regions") or {}
    tracks = stats.get("tracks") or {}
    if regions or tracks:
        region_text = " · ".join(f"{REGION_KO.get(k, k)} {v}" for k, v in regions.items())
        track_text = " · ".join(f"{TRACK_KO.get(k, k)} {v}" for k, v in tracks.items())
        out.append(f'<p class="note">지역: {_e(region_text)}<br>트랙: {_e(track_text)}</p>')
    if stats.get("deals"):
        out.append("<h3>투자·제휴 거래(자동 추출)</h3>")
        out.append(
            _table(
                ["날짜", "유형", "주체", "상대", "금액(USD 어림)"],
                [
                    [
                        _e(d.get("announced_on")),
                        _e(d.get("kind")),
                        _e(d.get("actor")),
                        f"{_e(d.get('counterparty'))} {citer.marks([d['item_id']])}",
                        f"{d['amount_usd'] / 1e6:,.0f}M" if d.get("amount_usd") else "",
                    ]
                    for d in stats["deals"]
                ],
            )
        )

    # 4. precedents
    out.append("<h2>4. 선례와 기저율</h2>")
    if content.get("base_rate"):
        out.append(f"<p><strong>외부 시각:</strong> {_e(content['base_rate'])}</p>")
    out.append(
        "".join(
            f'<div class="card"><h3>{_e(p.get("case"))}{_basis(p)}</h3>'
            f"<p><strong>닮은 점</strong> {_e(p.get('similarity'))}</p>"
            f"<p><strong>결과</strong> {_e(p.get('outcome'))} {citer.marks(p.get('item_ids'))}</p>"
            f"<p><strong>교훈</strong> {_e(p.get('lesson'))}</p></div>"
            for p in content["precedents"]
        )
        or '<p class="muted">근거 기간 안에서 찾은 선례가 없습니다.</p>'
    )

    # 5. implications
    out.append("<h2>5. DX 시사점</h2>")
    out.append(
        '<div class="grid">'
        + "".join(
            f'<div class="card"><p><span class="tag {i["impact"]}">{IMPACT_KO[i["impact"]]}</span>'
            f" <strong>{_e(i.get('area'))}</strong></p>"
            f"<p>1차 파급: {_e(i.get('first_order'))} {citer.marks(i.get('item_ids'))}</p>"
            f"<p>2차 파급: {_e(i.get('second_order'))}</p></div>"
            for i in content["implications"]
        )
        + "</div>"
    )

    # 6. assumptions and hypotheses
    out.append("<h2>6. 핵심 가정과 경쟁 가설</h2>")
    if content["assumptions"]:
        out.append("<h3>핵심 가정</h3>")
        out.append(_list([_e(a) for a in content["assumptions"]]))
    if content["hypotheses"]:
        out.append("<h3>경쟁 가설</h3>")
        out.append(
            _table(
                ["가설", "지지 근거", "반박 근거", "판단"],
                [
                    [
                        _e(h.get("statement")),
                        citer.marks(h.get("support_ids")) or "—",
                        citer.marks(h.get("counter_ids")) or "—",
                        _e(h.get("assessment")),
                    ]
                    for h in content["hypotheses"]
                ],
            )
        )

    # 7. signposts
    out.append("<h2>7. 관찰 지표</h2>")
    out.append(
        _table(
            ["지표", "기한", "가능성", "왜 중요한가"],
            [
                [
                    f"{_e(s.get('indicator'))} {citer.marks(s.get('item_ids'))}",
                    _e(s.get("window")),
                    f'<span class="tag">{_e(s["likelihood"])}</span>',
                    _e(s.get("why")),
                ]
                for s in content["signposts"]
            ],
        )
    )
    out.append(
        '<p class="note">가능성 어휘: '
        + " &lt; ".join(LIKELIHOOD)
        + ". 확신도와 따로 읽습니다.</p>"
    )

    # 8. limits and method
    out.append("<h2>8. 한계와 방법</h2>")
    out.append(_list([_e(g) for g in content["gaps"]]))
    method = [
        f"해석: {_e(plan.get('interpretation'))}" if plan.get("interpretation") else "",
        f"검색어: {_e(', '.join(plan.get('keywords') or []))}",
        f"인물: {_e(', '.join(plan.get('people') or []))}" if plan.get("people") else "",
        f"기업: {_e(', '.join(plan.get('companies') or []))}" if plan.get("companies") else "",
        f"의미 검색 문장: {_e(' / '.join(plan.get('queries') or []))}",
        f"수집 시작일: {_e(report.get('corpus_since'))} — 그 이전 사건은 수집 데이터에 없으며,"
        " '배경지식' 표시는 모델의 일반 지식이라 검증이 필요합니다.",
    ]
    out.append('<div class="note">' + _list([m for m in method if m]) + "</div>")

    # references
    out.append("<h2>근거</h2>")
    refs = []
    for item_id, number in sorted(citer.order.items(), key=lambda kv: kv[1]):
        src = sources[str(item_id)]
        refs.append(
            f'<li id="ref-{number}">[{number}] <a href="{_e(src["url"])}" target="_blank"'
            f' rel="noopener noreferrer">{_e(src["title"])}</a>'
            f' <span class="muted">— {_e(src["source"])}, {_e(src["date"])}</span></li>'
        )
    out.append('<ol class="refs" style="list-style:none;padding-left:0">' + "".join(refs) + "</ol>")

    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_e(title)}</title><style>{CSS}</style></head>"
        f"<body><main>{''.join(out)}</main></body></html>"
    )


# --- export document ------------------------------------------------------------------------


def document(report: dict[str, Any]) -> Doc:
    content: dict[str, Any] = report["content"]
    raw: dict[str, dict[str, Any]] = report["sources"]
    sources = {
        int(k): Source(item_id=int(k), title=v["title"], url=v["url"], source=v["source"])
        for k, v in raw.items()
    }

    def claims(rows: list[dict[str, Any]], key: str = "text") -> list[Block]:
        return [
            Block(str(r.get(key) or ""), refs=list(r.get("item_ids") or []), bullet=True)
            for r in rows
        ]

    bottom = content["bottom_line"]
    sections = [
        Section(
            "핵심 판단",
            [
                Block(bottom["judgement"], refs=list(bottom.get("item_ids") or [])),
                Block(
                    f"확신도 {CONFIDENCE_KO[bottom['confidence']]}"
                    f" — {bottom.get('confidence_reason', '')}"
                ),
                *claims(content["key_points"]),
            ],
        ),
        Section(
            "흐름",
            [
                Block(f"방향: {TRAJECTORY_KO[content['trajectory']['direction']]}"),
                *claims(content["trajectory"].get("points") or []),
                *[
                    Block(
                        f"{e.get('date')} · {e.get('actor')} · {e.get('action')}"
                        f" · {e.get('object')}"
                        f" ({MODE_KO[e['mode']]}): {e.get('summary')}",
                        refs=list(e.get("item_ids") or []),
                        bullet=True,
                    )
                    for e in content["events"]
                ],
            ],
        ),
    ]
    paths: list[Block] = []
    for path in content["actor_paths"]:
        paths.append(Block(str(path.get("actor")), heading=True))
        paths += [
            Block(
                str(p.get("text"))
                + (" (배경지식·검증 필요)" if p.get("basis") == "background" else ""),
                refs=list(p.get("item_ids") or []),
                bullet=True,
            )
            for p in path.get("past") or []
        ]
        paths.append(Block(f"읽기: {path.get('reading')}", refs=list(path.get("item_ids") or [])))
        paths.append(Block(f"다음 행보: {path.get('next')}"))
    if paths:
        sections.append(Section("핵심 주체의 궤적", paths))
    sections.append(
        Section(
            "주체 지형",
            [
                *claims(content["landscape"]),
                *[
                    Block(
                        f"{a.get('name')} ({KIND_KO.get(str(a.get('kind')), '기타')}): "
                        f"{a.get('position')} — {a.get('recent')}",
                        refs=list(a.get("item_ids") or []),
                        bullet=True,
                    )
                    for a in content["actors"]
                ],
            ],
        )
    )
    sections.append(
        Section(
            "선례와 기저율",
            [
                *(
                    [Block(f"외부 시각: {content['base_rate']}")]
                    if content.get("base_rate")
                    else []
                ),
                *[
                    Block(
                        f"{p.get('case')}"
                        + (" (배경지식·검증 필요)" if p.get("basis") == "background" else "")
                        + f": {p.get('outcome')} — {p.get('lesson')}",
                        refs=list(p.get("item_ids") or []),
                        bullet=True,
                    )
                    for p in content["precedents"]
                ],
            ],
        )
    )
    sections.append(
        Section(
            "DX 시사점",
            [
                Block(
                    f"[{IMPACT_KO[i['impact']]}] {i.get('area')}: {i.get('first_order')}"
                    f" → {i.get('second_order')}",
                    refs=list(i.get("item_ids") or []),
                    bullet=True,
                )
                for i in content["implications"]
            ],
        )
    )
    sections.append(
        Section(
            "핵심 가정과 경쟁 가설",
            [
                *[Block(f"가정: {a}", bullet=True) for a in content["assumptions"]],
                *[
                    Block(
                        f"가설: {h.get('statement')} — {h.get('assessment')}",
                        refs=[*(h.get("support_ids") or []), *(h.get("counter_ids") or [])],
                        bullet=True,
                    )
                    for h in content["hypotheses"]
                ],
            ],
        )
    )
    sections.append(
        Section(
            "관찰 지표",
            [
                Block(
                    f"{s.get('indicator')} ({s.get('window')}, 가능성 {s['likelihood']}):"
                    f" {s.get('why')}",
                    refs=list(s.get("item_ids") or []),
                    bullet=True,
                )
                for s in content["signposts"]
            ],
        )
    )
    if content["gaps"]:
        sections.append(Section("한계", [Block(str(g), bullet=True) for g in content["gaps"]]))
    return Doc(
        title=content.get("title") or report["topic"],
        subtitle=(
            f"동향 보고서 · {report['topic']} · {report['period_from']} ~ {report['period_to']}"
        ),
        sections=sections,
        sources=sources,
    )
