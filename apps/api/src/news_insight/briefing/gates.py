"""Publication quality gates (requirements §8). Blocking gates keep yesterday's briefing."""

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass

from news_insight.briefing.selection import Candidate, SelectionRules
from news_insight.digest.models import Digest, DigestStatus
from news_insight.sources.enums import Region


@dataclass(frozen=True)
class Gate:
    name: str
    label: str
    value: float
    threshold: float
    passed: bool
    blocking: bool = True

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


ADVISORY_REGION_MIN = {
    Region.JP.value: 0.05,
    Region.GREATER_CHINA.value: 0.04,
    Region.EU_OTHER.value: 0.06,
}


def _share(selected: list[Candidate], predicate: Callable[[Candidate], bool]) -> float:
    if not selected:
        return 0.0
    return sum(1 for c in selected if predicate(c)) / len(selected)


def evaluate(
    selected: list[Candidate],
    *,
    rules: SelectionRules,
    carded: int,
    story_ids: Mapping[int, int | None],
    digest: Digest | None,
    personas_ok: bool | None = None,
    strategy_ok: bool | None = None,
) -> list[Gate]:
    size = len(selected)
    domains = Counter(c.domain for c in selected)
    top_domain = max(domains.values(), default=0) / size if size else 0.0
    stories = [story_ids.get(c.item_id) for c in selected]
    repeated = sum(count - 1 for count in Counter(s for s in stories if s is not None).values())
    gates = [
        Gate(
            "translation",
            "번역·요약 성공률",
            carded / size if size else 0.0,
            0.98,
            size > 0 and carded / size >= 0.98,
        ),
        Gate(
            "duplicates",
            "중복 노출률",
            repeated / size if size else 0.0,
            0.05,
            size > 0 and repeated / size <= 0.05,
        ),
        Gate(
            "domain_cap",
            "단일 도메인 편중",
            top_domain,
            rules.domain_cap,
            size > 0 and top_domain <= rules.domain_cap,
        ),
        Gate(
            "korean",
            "한국 출처 비중",
            _share(selected, lambda c: c.region == Region.KR.value),
            rules.korean_min,
            _share(selected, lambda c: c.region == Region.KR.value) >= rules.korean_min,
        ),
        Gate(
            "official",
            "1차 공식 출처 비중",
            _share(selected, lambda c: c.official),
            rules.official_min,
            _share(selected, lambda c: c.official) >= rules.official_min,
        ),
        Gate(
            "independent",
            "독립 언론 비중",
            _share(selected, lambda c: c.independent),
            rules.independent_min,
            _share(selected, lambda c: c.independent) >= rules.independent_min,
        ),
    ]
    for track, minimum in rules.track_gate_min.items():
        count = sum(1 for c in selected if c.track == track)
        gates.append(
            Gate(f"track_{track}", f"{track} 트랙 최소 기사", count, minimum, count >= minimum)
        )
    claims_ok = digest is not None and digest.status is DigestStatus.PUBLISHED
    gates.append(
        Gate(
            "evidence",
            "다이제스트 근거(인사이트 출처 2개 이상)",
            1.0 if claims_ok else 0.0,
            1.0,
            claims_ok,
        )
    )
    if personas_ok is not None:
        gates.append(
            Gate(
                "personas",
                "30개 페르소나 인사이트(또는 no_signal)",
                float(personas_ok),
                1.0,
                personas_ok,
            )
        )
    if strategy_ok is not None:
        gates.append(
            Gate(
                "strategy",
                "전략 주장 출처 2개 이상·리뷰 통과",
                float(strategy_ok),
                1.0,
                strategy_ok,
            )
        )
    for region, floor in ADVISORY_REGION_MIN.items():
        share = sum(1 for c in selected if c.region == region) / size if size else 0.0
        gates.append(
            Gate(
                f"region_{region}",
                f"{region} 비중(권고)",
                share,
                floor,
                share >= floor,
                blocking=False,
            )
        )
    return gates
