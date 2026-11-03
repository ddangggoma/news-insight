# 주목 받는 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 독자 메뉴 「주목 받는」(`/spotlight`)에 분야별 화제 Top 10(05:00 브리핑 뒤 Claude CLI Opus 5.5가 확정)과 AI 모델 벤치마크 4곳의 차트·표를 보여 준다.

**Architecture:** 04:40 브리핑 고정 때 `spotlight.freeze`가 플랫폼 보정 화제성 점수로 분야별 후보를 저장한다. 05:00 `news-insight spotlight write`가 기존 `ClaudeCli`로 Opus를 한 번 호출해 순위·묶음·요약을 받고, 서버가 검증·분야별 대체 후 불변 발행본(`spotlights`·`spotlight_entries`)으로 저장한다. 벤치마크는 Celery beat가 매일 03:30 사이트별 수집기로 원본·정규화 점수를 저장하고, 웹은 사이트별 차트·표를 재현한다.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · Celery · Typer · Claude Code CLI / Next.js 16 · React 19 · Tailwind 4 · shadcn/ui Chart(Recharts 3.8) · TanStack Table v8(신규) · vitest

**Spec:** [2026-11-03-18-spotlight.md](2026-11-03-18-spotlight.md)

## Global Constraints

- 작업 위치: `/Users/ggoma/WorkSpace/NEWS_INSIGHT-wt-spotlight`(브랜치 `feat/spotlight`). dev 트리·라이브 트리에서 `compose up/down` 금지. `git add`는 경로를 지정(`-A` 금지).
- 테스트 DB: 이 작업 트리 전용 `news_insight_spotlight_test`(라이브 postgres `localhost:8720`, 확장 `pg_trgm`·`vector`), `TEST_REDIS_URL=redis://localhost:8721/15`. Node는 `~/.nvm/versions/node/v22.16.0/bin`.
- 모델 설정 `spotlight_model = "claude-opus-5-5"`, `spotlight_timeout_seconds = 900`.
- 기간: 브리핑 날짜 D의 전날 04:40 KST ~ D 04:40 KST(`first_seen_at`).
- 후보 수: 분야당 30, 제품 40. 발행 항목은 분야당 최대 10.
- 길이 상한: `title_ko` 120자, `summary` 260자, `why_hot` 140자, `rank_note` 140자.
- 재시도 일정은 기존 launchd 05·06·07·08·10시. 10시 실행(KST 시각 ≥ 10:00)이 마지막 시도.
- 운영 알림: `spotlight_missing` 10:30 KST 이후 미발행, `benchmark_stale` 사이트별 48시간 무갱신.
- 벤치마크 수집 Celery beat `benchmarks.collect` 03:30 KST.
- 화면 문구(그대로): 메뉴 "주목 받는", 빈 분야 "오늘은 기준을 넘는 화제가 없습니다", 대체 배지 "Opus 미작성", 생성 대기 띠 "오늘 목록 생성 중", 통계 순위 "통계 {n}위", Artificial Analysis 출처 "Data: Artificial Analysis".
- 섹션 키와 탭 이름: `news` 뉴스 · `product` 제품 · `oss` 오픈소스 · `interview` 인터뷰·발언 · `community` 커뮤니티 · `research` 연구 · `patent` 특허, 그리고 `overview` 전체 · `models` AI 모델.
- 벤치마크 사이트의 로고·브랜드 디자인은 쓰지 않는다. 원본 링크·갱신일·라이선스/출처를 각 카드에 표기.

## Review Focus

- **04:40 고정이 없는 날**: 05:00 `write`가 그 자리에서 `freeze`를 만들고 발행해야 한다 → Task 6 `test_write_freezes_when_missing`.
- **Opus가 같은 cid를 두 묶음·두 순위에 넣음**: 먼저 나온 것만 남기고 뒤의 것은 버린다 → Task 6 `test_cid_used_twice_kept_once`.
- **게시 시각이 없거나 미래(시간대 오파싱)**: 경과시간 하한 2시간으로 처리되고 예외가 나지 않는다 → Task 2 `test_future_published_at_uses_floor`.
- **전날 발행본이 없는 날(첫날·공백)**: 모든 항목이 NEW, 오류 없음 → Task 8 `test_no_previous_day_all_new`.
- **벤치마크 사이트가 JSON 대신 HTML(차단 페이지)을 돌려줌**: 수집 실패로 기록, 마지막 정상 스냅샷 유지, 다른 사이트는 계속 → Task 12 `test_html_response_is_drift_and_keeps_last_good`.

---

## Part 1 — 「주목 받는」 (PR 1: P1~P3)

### Task 1: 저장 모델과 마이그레이션

**Files:**
- Create: `apps/api/src/news_insight/spotlight/__init__.py`, `apps/api/src/news_insight/spotlight/models.py`
- Create: `apps/api/migrations/versions/0044_spotlight.py`
- Modify: `apps/api/src/news_insight/db.py`(모델 import 등록 방식이 있으면 그에 맞춤)
- Test: `apps/api/tests/spotlight/__init__.py`, `apps/api/tests/spotlight/test_models.py`

**Interfaces:**
- Produces:
  - `SpotlightFreeze(id, spotlight_date: date unique, frozen_at, candidates: dict[str, list[dict]] JSONB)`
  - `SpotlightStatus(StrEnum)`: `PUBLISHED="published"`, `FAILED="failed"`
  - `Spotlight(id, spotlight_date: date unique, status, model: str, cost_usd: float|None, headline: str, benchmark_note: str, freeze_id FK, error: str|None, generated_at)`
  - `SpotlightEntry(id, spotlight_id FK cascade, section: str(20), rank: int, stat_rank: int, key: str(200), item_ids: list[int] JSONB, title_ko: str, product_name: str|None, summary: str, why_hot: str, rank_note: str|None, metrics: dict JSONB, fallback: bool)`, 인덱스 `(spotlight_id, section, rank)` unique

- [ ] **Step 1: 테스트 DB 준비**

```bash
cd /Users/ggoma/WorkSpace/NEWS_INSIGHT-live && docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "create database news_insight_spotlight_test" && psql -U "$POSTGRES_USER" -d news_insight_spotlight_test -c "create extension if not exists pg_trgm; create extension if not exists vector"'
```
이후 모든 pytest는 `cd apps/api && TEST_DATABASE_URL=postgresql+psycopg://news:news-dev-password@localhost:8720/news_insight_spotlight_test TEST_REDIS_URL=redis://localhost:8721/15 uv run pytest ...`(아래 `PYTEST`로 줄여 씀).

- [ ] **Step 2: 실패하는 테스트 작성** — `test_entry_unique_rank_per_section`: 같은 spotlight·section·rank 두 행 flush 시 `IntegrityError`. `test_spotlight_date_unique`: 같은 날짜 두 `Spotlight` flush 시 `IntegrityError`.
- [ ] **Step 3: 실행해 실패 확인** — `PYTEST tests/spotlight/test_models.py -v` → import 오류로 FAIL.
- [ ] **Step 4: 모델과 0044 마이그레이션 작성** — `briefing/models.py` 형식을 따른다(`str_enum`, `DateTime(timezone=True)`). 마이그레이션은 revision `"0044"`, down_revision `"0043"`, 세 테이블 생성/삭제만.
- [ ] **Step 5: 통과 확인** — `PYTEST tests/spotlight/test_models.py -v` PASS, `scripts/dev.sh alembic-check` 통과.
- [ ] **Step 6: 커밋** — `git add apps/api/src/news_insight/spotlight apps/api/migrations/versions/0044_spotlight.py apps/api/tests/spotlight && git commit -m "feat(spotlight): freeze, spotlight and entry tables (plan 18)"`

### Task 2: 플랫폼 보정 화제성 점수

**Files:**
- Create: `apps/api/src/news_insight/spotlight/scoring.py`
- Test: `apps/api/tests/spotlight/test_scoring.py`

**Interfaces:**
- Produces:
  - `PLATFORM_METRICS: dict[str, tuple[str, ...]]` — 소스 operator → 합산할 metrics 키. 값: `"Algolia (HN Search)"`·`"Y Combinator"` → `("points","comments")`, `"Mastodon gGmbH"`·`"Fosstodon"`·`"mstdn.jp"` → `("favourites","reblogs","replies")`, `"Bluesky Social PBC"` → `("likes","reposts","replies")`, `"DEV Community"` → `("reactions","comments")`, V2EX·Stack 계열(`score`·`answers` 키를 가진 operator) → `("score","answers")`, `"GitHub"`(github_trending) → `("trending_stars_daily",)`, `"Hugging Face"` → `("trending","likes")`(앞 키가 있으면 그것만), YouTube(`"Google LLC (YouTube Data API)"`) → `("views",)`, HF Daily Papers → `("upvotes","comments")`
  - `engagement(operator: str, metrics: dict[str, int]) -> int | None` — 매핑 없거나 키가 하나도 없으면 None
  - `velocity(value: int, published: datetime | None, first_seen: datetime, at: datetime) -> float` — `log1p(value / max(hours, 2))`, hours = (at − (published or first_seen)) 시간, 음수면 하한 적용
  - `@dataclass(frozen=True) PlatformStats(mean: float, std: float, n: int)`
  - `MIN_SAMPLE = 30`
  - `zscore(v: float, stats: PlatformStats | None, fallback: PlatformStats) -> float` — stats가 None이거나 n < 30이면 fallback 사용, std가 0이면 0.0
  - `platform_stats(session, *, at: datetime, days: int = 7) -> tuple[dict[str, PlatformStats], PlatformStats]` — operator별 + 전체(community·oss) 분포, 각 항목의 최신 metrics 스냅샷 기준

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_hn_sums_points_and_comments():
    assert engagement("Algolia (HN Search)", {"points": 400, "comments": 12}) == 412

def test_unknown_operator_is_none():
    assert engagement("Nobody", {"points": 3}) is None

def test_hours_floor_two():
    at = datetime(2026, 11, 4, 19, 40, tzinfo=UTC)
    assert velocity(100, at - timedelta(minutes=30), at, at) == pytest.approx(math.log1p(50))

def test_future_published_at_uses_floor():
    at = datetime(2026, 11, 4, 19, 40, tzinfo=UTC)
    assert velocity(100, at + timedelta(hours=9), at, at) == pytest.approx(math.log1p(50))

def test_small_platform_uses_fallback():
    fb = PlatformStats(mean=1.0, std=1.0, n=500)
    assert zscore(3.0, PlatformStats(mean=0.0, std=1.0, n=10), fb) == pytest.approx(2.0)

def test_zero_std_is_zero():
    assert zscore(5.0, PlatformStats(2.0, 0.0, 100), PlatformStats(0, 1, 100)) == 0.0
```
`test_platform_stats_uses_latest_snapshot`(db): 한 항목에 스냅샷 2개(값 10 → 100)를 넣으면 분포에 100만 반영.

- [ ] **Step 2: 실패 확인** — `PYTEST tests/spotlight/test_scoring.py -v` FAIL.
- [ ] **Step 3: 구현** — `platform_stats`는 `item_metric_snapshots`에서 `DISTINCT ON (item_id) ORDER BY captured_at DESC`로 최신값을 가져와 `velocity` 분포의 평균·표준편차를 계산.
- [ ] **Step 4: 통과 확인** — 같은 명령 PASS.
- [ ] **Step 5: 커밋** — `feat(spotlight): platform-normalised engagement score`

### Task 3: 후보 선정 — 기간, 뉴스, 커뮤니티, 중복 처리

**Files:**
- Create: `apps/api/src/news_insight/spotlight/candidates.py`
- Test: `apps/api/tests/spotlight/test_candidates.py`

**Interfaces:**
- Consumes: Task 2 `engagement`, `velocity`, `zscore`, `platform_stats`
- Produces:
  - `SECTIONS: tuple[str, ...] = ("news","product","oss","interview","community","research","patent")`
  - `LIMITS = {"product": 40}`, 기본 30
  - `@dataclass Candidate(cid: str, section: str, key: str, item_ids: list[int], title_ko: str, summary_ko: str, url: str, metrics: dict[str, Any], score: float, stat_rank: int)` + `to_json() -> dict`
  - `window(day: date) -> tuple[datetime, datetime]` — UTC aware
  - `collect_candidates(session, *, day: date, now: datetime) -> dict[str, list[Candidate]]` — 모든 SECTIONS 키를 항상 포함(빈 목록 가능)
  - 내부 공통: `_eligible_items(session, start, end)` — `item_dedup.duplicate_of IS NULL`, `canary = false`; 사건(story)에 속하면 대표 항목 1건으로 접는 `_fold_stories(...)`
  - cid 형식: 섹션 첫 글자 + 일련번호(`n1`, `p1`, `o1`, `i1`, `c1`, `r1`, `t1`)
  - 키 형식: 사건 `story:{id}`, 항목 `item:{id}`
- 뉴스: news 트랙 사건, 점수 = `source_count` × 100 + 커뮤니티 언급 수 × 10 + 사건 내 커뮤니티 z 최대값. 하한 `source_count ≥ 2`. `metrics = {"source_count", "community_mentions"}`
- 커뮤니티: community 트랙 항목, 점수 = z. 하한 z ≥ 1.0. `metrics`는 원래 지표 + `{"platform": operator}`

- [ ] **Step 1: 실패하는 테스트 작성** (db, `ingest_items`·`build_source`·스토리 생성은 `tests/briefing/test_publish.py`·`tests/stories` 방식 재사용)
  - `test_window_is_0440_kst_to_0440_kst`: `window(date(2026,11,4)) == (datetime(2026,11,2,19,40,tzinfo=UTC), datetime(2026,11,3,19,40,tzinfo=UTC))`
  - `test_items_outside_window_excluded`
  - `test_one_entry_per_story`: 같은 사건 3개 기사 → 뉴스 후보 1건, `item_ids` 길이 3
  - `test_duplicate_items_excluded`: `duplicate_of`가 있는 항목은 어느 섹션에도 없음
  - `test_news_ranked_by_source_count`: source_count 5 사건이 3 사건보다 `stat_rank` 앞
  - `test_news_below_two_sources_excluded`
  - `test_community_below_z_one_excluded`
  - `test_all_sections_present_even_if_empty`: `set(result) == set(SECTIONS)`
- [ ] **Step 2: 실패 확인** — `PYTEST tests/spotlight/test_candidates.py -v` FAIL.
- [ ] **Step 3: 구현** — `window`, `_eligible_items`, `_fold_stories`, 뉴스·커뮤니티 빌더, `collect_candidates`(나머지 섹션은 Task 4 전까지 빈 목록).
- [ ] **Step 4: 통과 확인**.
- [ ] **Step 5: 커밋** — `feat(spotlight): candidate window, news and community sections`

### Task 4: 후보 선정 — 제품, 오픈소스, 인터뷰, 연구, 특허

**Files:**
- Modify: `apps/api/src/news_insight/spotlight/candidates.py`
- Test: `apps/api/tests/spotlight/test_candidates.py`

**Interfaces:**
- Consumes: Task 3의 `Candidate`, `_eligible_items`, `_fold_stories`
- Produces(섹션 빌더 규칙):
  - 제품: 카드 `signal_type == "launch"`인 사건·항목, 점수 = `source_count` × 100 + 커뮤니티 z 합. 하한 `source_count ≥ 2` 또는 z 합 ≥ 1.0. 상한 40
  - 오픈소스: oss 트랙 항목, 점수 = z + 24시간 안에 같은 `item_refs`(`github`·`hf`) 값을 가진 다른 글 수 × 0.5. 하한 z ≥ 1.0 또는 언급 ≥ 2. `metrics`에 `mentions`
  - 인터뷰: 카테고리 `podcast_newsletter`·`video_channel` 항목 + 제목이 `INTERVIEW_PATTERN`과 맞는 news 항목. `INTERVIEW_PATTERN = re.compile(r"\b(interview|keynote|podcast|fireside|says|Q&A)\b|인터뷰|대담|기조연설|CEO|CTO", re.I)`. 점수 = YouTube 조회수 z(있으면) + 보도·언급 수. 하한 없음(후보 30건 상한만)
  - 연구: research_ip 트랙 논문, 점수 = 24시간 안에 뉴스·커뮤니티에서 같은 `doi`·`arxiv` 참조를 가진 글 수 × 10 + HF Daily Papers `upvotes` z. 하한 언급 ≥ 1 또는 upvotes ≥ 10. `metrics`에 `mentions`, `upvotes`
  - 특허: 카드 `signal_type == "ip"` 사건 + 카테고리 `patent_office` 항목 중 언급 ≥ 1, 점수 = 보도·언급 수. 하한 `source_count ≥ 1`

- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_product_limit_is_forty`: launch 사건 45개 → 40건
  - `test_oss_mentions_raise_rank`: z가 같은 저장소 두 개 중 커뮤니티 언급 3회인 쪽이 앞
  - `test_interview_includes_video_and_title_pattern`: video_channel 항목 1 + 제목 "CEO interview" 뉴스 1 → 2건, 일반 뉴스는 제외
  - `test_research_counts_arxiv_mentions`: 논문(arxiv 2610.00001) + 같은 arxiv를 언급한 HN 글 2개 → `metrics["mentions"] == 2`
  - `test_research_without_mentions_or_upvotes_excluded`
  - `test_patent_ip_story_included`
- [ ] **Step 2: 실패 확인**. **Step 3: 구현**. **Step 4: 통과 확인**.
- [ ] **Step 5: 커밋** — `feat(spotlight): product, open-source, interview, research and patent sections`

### Task 5: 보강 수집 — YouTube 조회수, HF Daily Papers

**Files:**
- Modify: `apps/api/src/news_insight/collect/json_api.py`, `apps/api/src/news_insight/collect/presets.py`, `apps/api/src/news_insight/stories/refs.py:7`
- Modify: `apps/api/catalog/sources.yaml`(새 소스 `hf-daily-papers-api`)
- Test: `apps/api/tests/collect/test_json_api.py`(기존 파일에 추가), `apps/api/tests/stories/test_refs.py`(있으면 추가, 없으면 생성)

**Interfaces:**
- Produces:
  - 프리셋 `youtube_playlist`에 `"video_stats": True` 추가. `JsonApiCollector.collect`는 `video_stats`가 참이면 수집한 영상 id를 50개씩 `https://www.googleapis.com/youtube/v3/videos?part=statistics&id=...`로 조회(같은 인증 헤더)해 `metrics`에 `views`·`likes`·`comments`를 더한다. 통계 호출 실패는 항목 수집을 막지 않는다(지표 없이 반환).
  - 함수 `_youtube_stats(fetcher, ids: list[str], headers: dict[str, str]) -> dict[str, dict[str, int]]`
  - 프리셋 `hf_daily_papers`: `list_path=""`, fields `id: "paper.id"`, `title: "title"`, `summary: "summary"`, `published_at: "publishedAt"`, `url: []`, `url_template: "https://huggingface.co/papers/{paper.id}"`, metrics `upvotes: "paper.upvotes"`, `comments: "numComments"`
  - `ARXIV` 정규식에 `huggingface\.co/papers/` 접두 허용
  - 카탈로그 소스: `key: hf-daily-papers-api`, `name: Hugging Face Daily Papers (API)`, `track: research_ip`, `category: academic_paper`, `access_method: json_api`, `endpoint_url: https://huggingface.co/api/daily_papers?limit=100`, `operator: Hugging Face Daily Papers`, `config: {preset: hf_daily_papers}`, 나머지는 `hf-papers`와 같게. 기존 `hf-papers`(사이트맵이 Spaces 페이지를 모음)는 `status: paused`, `paused_reason: "sitemap collects Spaces, not papers; replaced by hf-daily-papers-api"`.

- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_youtube_statistics_merged`: 가짜 fetcher가 playlistItems 2건과 videos 응답 `{"items":[{"id":"a","statistics":{"viewCount":"480000","likeCount":"9000","commentCount":"300"}}]}`를 돌려주면 항목 a의 `metrics == {"views":480000,"likes":9000,"comments":300}`, 항목 b는 `{}`
  - `test_youtube_statistics_failure_keeps_items`: videos 호출이 500이면 항목 2건, metrics 비어 있음
  - `test_hf_daily_papers_preset`: `daily_papers` 1건(위 형식) → url `https://huggingface.co/papers/2610.39278`, `metrics == {"upvotes":5,"comments":1}`
  - `test_hf_papers_url_yields_arxiv_ref`: `extract_refs("https://huggingface.co/papers/2610.39278")`에 `("arxiv","2610.39278")` 포함
- [ ] **Step 2: 실패 확인** — `PYTEST tests/collect/test_json_api.py tests/stories -k "youtube or hf_" -v`.
- [ ] **Step 3: 구현**. **Step 4: 통과 확인**.
- [ ] **Step 5: 커밋** — `feat(collect): YouTube view counts and the Hugging Face daily papers API`

### Task 6: freeze와 Opus write

**Files:**
- Create: `apps/api/src/news_insight/spotlight/service.py`, `apps/api/src/news_insight/spotlight/prompts.py`
- Modify: `apps/api/src/news_insight/jobs/tasks.py:103-119`(briefing_freeze_task에 spotlight freeze 추가), `apps/api/src/news_insight/config.py`
- Test: `apps/api/tests/spotlight/test_service.py`

**Interfaces:**
- Consumes: Task 3·4 `collect_candidates`, `Candidate`; `news_insight.digest.claude.ClaudeClient`, `ClaudeResult`, `ClaudeError`
- Produces:
  - `config.Settings.spotlight_model: str = "claude-opus-5-5"`, `spotlight_timeout_seconds: int = 900`
  - `prompts.SYSTEM_PROMPT: str`(설계 §5.3의 규칙 그대로, 한국어), `prompts.INSTRUCTION: str`, `prompts.OUTPUT_SCHEMA: dict`(설계 §5.4)
  - `freeze(session, *, day: date, now: datetime) -> SpotlightFreeze` — 같은 날짜면 기존 것을 반환
  - `write(session, *, day: date, now: datetime, client: ClaudeClient, model: str, final_attempt: bool, benchmarks: dict | None = None) -> Spotlight` — 이미 PUBLISHED면 그대로 반환. freeze가 없으면 만든다. 성공 시 `cost_usd = ClaudeResult.cost_usd`, `model = ClaudeResult.model`. Claude 실패 시 `final_attempt`가 거짓이면 `status=FAILED`·`error` 기록 후 `ClaudeError`를 다시 던지고, 참이면 전 분야 대체로 PUBLISHED
  - `build_payload(freeze, previous: dict[str, list[str]], benchmarks: dict | None) -> dict` — 설계 §5.2 형식. 후보는 `cid,title_ko,summary_ko,metrics,stat_rank`만 담음
  - `validate(output: dict, candidates: dict[str, list[dict]]) -> dict[str, list[dict]]` — 검증된 항목 목록(분야별, 최종 rank 1..n로 다시 번호)
  - 대체 항목: stat_rank 상위 10, `summary = summary_ko`, `why_hot = ""`, `fallback = True`
  - 제품 묶음 `metrics`: 구성 후보 metrics의 수치 합 + `{"group_size": n}`; `key = "product:" + product_name.casefold()`의 공백→하이픈

- [ ] **Step 1: 실패하는 테스트 작성** (가짜 클라이언트는 `tests/digest/test_service.py`의 `FakeClaude` 형식, `generate(payload, *, schema, model, system=None, instruction=None)`)
  - `test_freeze_is_idempotent`
  - `test_write_freezes_when_missing`
  - `test_valid_output_published`: 뉴스 2건 출력 → 엔트리 2건, rank 1·2, `fallback is False`, `Spotlight.status == PUBLISHED`, `model == "claude-opus-5-5"`
  - `test_unknown_cid_dropped`, `test_cross_section_cid_dropped`
  - `test_cid_used_twice_kept_once`: 제품 묶음 두 개에 `p1`이 모두 있으면 둘째 묶음에서 `p1` 제거(남는 cid가 없으면 그 묶음 제외)
  - `test_more_than_ten_truncated`
  - `test_overlong_fields_dropped`: summary 261자 항목은 버림
  - `test_empty_section_falls_back`: 커뮤니티 출력 0건·후보 3건 → 엔트리 3건 모두 `fallback is True`
  - `test_rank_note_kept_and_stat_rank_stored`
  - `test_product_group_sums_metrics`: `cids=["p1","p2"]`, 각 source_count 3·2 → `metrics["source_count"] == 5`, `item_ids`는 두 후보 합집합
  - `test_claude_error_not_final_records_failed`: `pytest.raises(ClaudeError)`, 행 status FAILED
  - `test_claude_error_final_publishes_fallback`: 모든 분야 `fallback is True`, status PUBLISHED
  - `test_published_is_immutable`: 두 번째 `write`는 클라이언트를 부르지 않고 같은 행 반환
- [ ] **Step 2: 실패 확인** — `PYTEST tests/spotlight/test_service.py -v`.
- [ ] **Step 3: 구현** — `briefing_freeze_task`에서 레이더 스냅샷과 같은 `session.begin_nested()` + 예외 로그로 `spotlight.service.freeze` 호출.
- [ ] **Step 4: 통과 확인** — 위 명령과 `PYTEST tests/jobs -v` PASS.
- [ ] **Step 5: 커밋** — `feat(spotlight): 04:40 freeze and the Opus writer with validation and fallback`

### Task 7: CLI, 05:00 작업, 운영 알림

**Files:**
- Modify: `apps/api/src/news_insight/cli.py`(새 `spotlight_app`), `scripts/dev.sh:78-88`(digest), `apps/api/src/news_insight/ops/checks.py`
- Test: `apps/api/tests/test_cli.py`(추가), `apps/api/tests/ops/test_checks.py`(추가)

**Interfaces:**
- Consumes: Task 6 `freeze`, `write`, `Spotlight`
- Produces:
  - `news-insight spotlight freeze [--date]`, `news-insight spotlight write [--date] [--model]` — `write`는 `_claude()`와 같은 `ClaudeCli`를 `timeout_seconds=settings.spotlight_timeout_seconds`로 만들고, `final_attempt = 현재 KST 시각 ≥ 10:00`. 이미 발행이면 `"{day} spotlight already published; nothing to do"` 출력. `ClaudeError`면 종료 코드 1.
  - `dev.sh digest()`: `daily publish` 다음 줄에 `(cd "$API" && uv run --env-file "$ROOT/.env" news-insight spotlight write) || echo "spotlight not written; the next digest run retries" >&2` — 브리핑 `status`에 영향 없음. 기존 revalidate 호출을 이 뒤로 옮겨 두 결과를 함께 새로 고침
  - `SPOTLIGHT_DEADLINE = time(10, 30)`, `check_spotlight(session, *, now) -> list[Finding]` → `Finding("spotlight_missing", Severity.WARNING, f"{today} 주목 받는 목록이 발행되지 않았습니다", "Claude 로그인·한도와 ops/logs/digest.log를 확인하세요.")`; `run_checks`에 추가

- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_spotlight_write_noop_when_published`(CliRunner, `tests/test_cli.py` 형식)
  - `test_check_spotlight_before_deadline_quiet`: 10:29 KST, 미발행 → `[]`
  - `test_check_spotlight_after_deadline_warns`: 10:31 KST, 미발행 → key `spotlight_missing`
  - `test_check_spotlight_published_quiet`
- [ ] **Step 2: 실패 확인**. **Step 3: 구현**. **Step 4: 통과 확인** — `PYTEST tests/test_cli.py tests/ops -k spotlight -v`.
- [ ] **Step 5: 커밋** — `feat(spotlight): CLI, 05:00 digest step and the missing-list alert`

### Task 8: 공개 API

**Files:**
- Create: `apps/api/src/news_insight/public/spotlight.py`
- Modify: `apps/api/src/news_insight/public/routes.py`(`@router.get("/spotlight")`)
- Test: `apps/api/tests/public/test_spotlight_api.py`

**Interfaces:**
- Consumes: Task 1 모델
- Produces:
  - `SpotlightEntryOut(rank, stat_rank, change: Literal["new","up","down","same"], change_by: int, key, item_ids, title_ko, product_name, summary, why_hot, rank_note, metrics, fallback, url: str | None)` — url은 대표 항목(item_ids[0])의 원문
  - `SpotlightView(date: date | None, generating: bool, headline: str, benchmark_note: str, sections: dict[str, list[SpotlightEntryOut]], available_dates: list[date], generated_at: datetime | None)`
  - `spotlight_view(session, *, day: date | None, now: datetime) -> SpotlightView` — day가 없으면 가장 최근 PUBLISHED; 오늘(KST) 발행본이 없으면 `generating=True`. 없는 날짜를 요청하면 404. `available_dates` 최근 60개
  - 라우트 `GET /api/public/spotlight?date=YYYY-MM-DD`

- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_latest_published_by_default`
  - `test_generating_when_today_missing`: 어제만 발행 → `date == 어제`, `generating is True`
  - `test_change_new_up_down`: 어제 key A 3위·B 1위, 오늘 A 1위·B 2위·C 3위 → A `up` 2, B `down` 1, C `new`
  - `test_no_previous_day_all_new`
  - `test_unknown_date_404`
  - `test_sections_include_all_keys`: 모든 SECTIONS 키 존재(빈 목록 포함)
- [ ] **Step 2: 실패 확인** — `PYTEST tests/public/test_spotlight_api.py -v`. **Step 3: 구현**. **Step 4: 통과 확인**.
- [ ] **Step 5: 커밋** — `feat(public): spotlight endpoint with day-over-day change`

### Task 9: `/spotlight` 화면과 메뉴

**Files:**
- Create: `apps/web/lib/spotlight-types.ts`, `apps/web/app/(reader)/spotlight/page.tsx`, `apps/web/app/(reader)/spotlight/loading.tsx`
- Create: `apps/web/components/reader/spotlight/entry-row.tsx`, `section-list.tsx`, `overview.tsx`, `spotlight-tabs.tsx`, `date-select.tsx`
- Modify: `apps/web/components/reader/reader-header.tsx`(READER_NAV 두 번째에 `{ href: "/spotlight", label: "주목 받는", icon: Flame, match: ["/spotlight"] }`), `apps/web/lib/reader-api.ts`(`REVALIDATE.spotlight = 600`)
- Test: `apps/web/tests/spotlight.test.tsx`, `apps/web/tests/reader-nav.test.tsx:17`

**Interfaces:**
- Consumes: Task 8 `SpotlightView` 형식(TS 타입으로 그대로 옮김)
- Produces:
  - `SECTION_LABEL: Record<SectionKey, string>`(Global Constraints의 탭 이름)
  - `<EntryRow entry={SpotlightEntry} />` — 순위, 변화 배지(▲n·▼n·NEW), `stat_rank !== rank`면 "통계 {n}위", 제목(원문 링크), 요약, 화제 이유, rank_note, 지표 칩, `fallback`이면 "Opus 미작성" 배지
  - `<SectionList entries />` — 빈 목록이면 "오늘은 기준을 넘는 화제가 없습니다"
  - `<Overview view />` — headline + 분야별 Top 3, 각 묶음 제목은 `?tab=<section>` 링크
  - 페이지: `?tab=`(기본 overview)과 `?date=`를 읽고, `generating`이면 상단에 "오늘 목록 생성 중" 띠. AI 모델 탭은 Part 2에서 추가(이 단계에서는 탭 목록에 없음)

- [ ] **Step 1: 실패하는 테스트 작성**

```tsx
it("shows the statistical rank when Opus moved the entry", () => {
  render(<EntryRow entry={{ ...base, rank: 2, stat_rank: 4 }} />);
  expect(screen.getByText("통계 4위")).toBeInTheDocument();
});
it("marks fallback entries", () => {
  render(<EntryRow entry={{ ...base, fallback: true }} />);
  expect(screen.getByText("Opus 미작성")).toBeInTheDocument();
});
it("shows NEW and arrows", () => { /* change new → "NEW", up 2 → "▲2", down 1 → "▼1" */ });
it("explains an empty section", () => {
  render(<SectionList entries={[]} />);
  expect(screen.getByText("오늘은 기준을 넘는 화제가 없습니다")).toBeInTheDocument();
});
```
`reader-nav.test.tsx` 기대값: `["데일리 브리핑", "주목 받는", "탐색", "레이더", "투자·제휴", "특허", "로드맵", "동향 보고서 작성"]`.
- [ ] **Step 2: 실패 확인** — `cd apps/web && PATH=$HOME/.nvm/versions/node/v22.16.0/bin:$PATH npx vitest run tests/spotlight.test.tsx tests/reader-nav.test.tsx`.
- [ ] **Step 3: 구현** — 기존 `patents/page.tsx`와 `roadmap-tabs.tsx`의 구조·클래스 관례를 따른다(`requireUser()`, `readerGet`, `AppLink`).
- [ ] **Step 4: 통과 확인** — 같은 명령 PASS, `scripts/dev.sh web-check` 통과.
- [ ] **Step 5: 화면 확인** — 작업 트리 e2e DB로 API·웹을 띄워 `/spotlight` 전체·뉴스·빈 분야, 라이트·다크, 375px 폭을 스크린샷으로 확인.
- [ ] **Step 6: 커밋** — `feat(web): 주목 받는 menu with daily top 10s`

### Task 10: Part 1 검증과 PR

- [ ] **Step 1:** `scripts/dev.sh verify` 전 단계 통과.
- [ ] **Step 2:** 실제 Claude CLI로 1회 생성 시험: 작업 트리 DB에 라이브 데이터 일부를 넣기 어렵다면 라이브 배포 뒤 `news-insight spotlight write --date <오늘>`로 확인(배포는 사용자 승인 뒤).
- [ ] **Step 3:** PR 생성(본문에 설계서·계획 링크, 스크린샷), CI 통과 확인. 병합·배포는 사용자 승인 뒤 `NEWS_INSIGHT-live/scripts/deploy.sh`.

---

## Part 2 — AI 모델 벤치마크 (PR 2: P4~P5)

### Task 11: 벤치마크 저장 모델과 모델 이름 통일

**Files:**
- Create: `apps/api/src/news_insight/benchmarks/__init__.py`, `models.py`, `names.py`
- Create: `apps/api/migrations/versions/0045_benchmarks.py`
- Test: `apps/api/tests/benchmarks/__init__.py`, `test_names.py`

**Interfaces:**
- Produces:
  - `BenchmarkSnapshot(id, site: str(40), release: str(40), fetched_at, sha256: str(64), raw: dict JSONB)` — unique `(site, sha256)`
  - `BenchmarkScore(id, snapshot_id FK cascade, site, board: str(60), model_raw: str(200), model_id FK nullable, org: str|None, config: str|None, metric: str(60), value: float, ci_low: float|None, ci_high: float|None, extra: dict JSONB)`
  - `AiModel(id, name unique, org, open_weights: bool|None)`, `AiModelAlias(alias unique, model_id FK)`
  - `normalize(name: str) -> str` — 소문자, 공백·밑줄·마침표 → 하이픈, 연속 하이픈 축약, 괄호 내용은 `config`로 분리하지 않고 제거, 끝의 `-20\d{6}`·`-\d{4}-\d{2}-\d{2}` 날짜 제거
  - `resolve_model(session, raw: str, org: str | None) -> int | None` — alias 정확 일치 → normalize 일치 → None. None이면 아무것도 만들지 않는다(콘솔에서 연결)

- [ ] **Step 1: 실패하는 테스트 작성**

```python
@pytest.mark.parametrize("raw,expected", [
    ("Claude Opus 5.5", "claude-opus-5-5"),
    ("claude-opus-5.5", "claude-opus-5-5"),
    ("Gemini 4 Carbon (High)", "gemini-4-carbon"),
    ("gpt-5-5-2026-06-01", "gpt-5-5"),
    ("  GPT_6  Astra ", "gpt-6-astra"),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected
```
`test_resolve_by_alias_then_normalized`(db), `test_unknown_returns_none`.
- [ ] **Step 2: 실패 확인**. **Step 3: 구현**(마이그레이션 0045, down_revision "0044"). **Step 4: 통과 확인**, `scripts/dev.sh alembic-check`.
- [ ] **Step 5: 커밋** — `feat(benchmarks): snapshot, score and model registry tables`

### Task 12: 사이트별 수집기와 03:30 작업

**Files:**
- Create: `apps/api/src/news_insight/benchmarks/sources/__init__.py`, `deepswe.py`, `livebench.py`, `lmarena.py`, `artificial_analysis.py`, `apps/api/src/news_insight/benchmarks/service.py`
- Create: `apps/api/tests/benchmarks/fixtures/`(deepswe.json, livebench_main.js 일부, livebench_table.csv, livebench_cost.csv, livebench_categories.json, lmarena_text_style_control.json, artificial_analysis.json)
- Modify: `apps/api/src/news_insight/jobs/tasks.py`, `apps/api/src/news_insight/jobs/celery_app.py`(beat `benchmarks-collect` crontab 3:30), `apps/api/src/news_insight/ops/checks.py`, `compose.yaml`(`SOURCE_SECRET_ARTIFICIAL_ANALYSIS_KEY`), `.env.example`
- Test: `apps/api/tests/benchmarks/test_sources.py`, `test_service.py`

**Interfaces:**
- Produces:
  - `@dataclass ScoreRow(board, model_raw, org, config, metric, value, ci_low=None, ci_high=None, extra=dict)`
  - `@dataclass SiteSnapshot(site: str, release: str, raw: dict, rows: list[ScoreRow])`
  - `class BenchmarkError(Exception)` with `code: str`(`selector_drift`·`http_error`·`config_error`)
  - 각 모듈 `fetch(fetcher: SafeFetcher, now: datetime) -> SiteSnapshot`, 모듈 상수 `SITE`, `TITLE`, `SOURCE_URL`, `LICENSE`, `ATTRIBUTION`
  - DeepSWE: `https://deepswe.datacurve.ai/artifacts/v1/leaderboard-live.json`의 `rows` → board `"v1.1"`(응답의 scope/버전 값이 있으면 그것), metric `pass_at_1`(ci는 `ci_lo`·`ci_hi`), `config = reasoning_effort`, `extra`에 `mean_cost_usd`·출력 토큰·단계 등 행의 나머지 수치 필드
  - LiveBench: `https://livebench.ai/`의 main JS에서 `"20\d\d-\d\d-\d\d"` 날짜를 모아 최신부터 `/data/YYYYMMDD/table.csv`가 200인 첫 날짜를 release로. `table.csv` 각 열 → metric(열 이름 그대로), `overall` = 영역 평균은 사이트가 주는 값이 있으면 그것, 없으면 계산하지 않고 표시만 생략. `cost.csv` → metric `cost_per_success`. `categories.json`·`breakdown.json`은 `raw`에 보관하고 행 펼침용으로 `extra`에 넣는다
  - LMArena: `https://datasets-server.huggingface.co/filter?dataset=lmarena-ai/leaderboard-dataset&config=<board>&split=latest&where="category"='overall'&offset=<n>&length=100`을 페이지로 끝까지. boards = `("text_style_control","webdev","vision_style_control","search_style_control","agent")`. metric `rating`, ci `rating_lower`·`rating_upper`, `extra = {rank, vote_count, license, leaderboard_publish_date}`
  - Artificial Analysis: `GET https://artificialanalysis.ai/api/v2/language/models`, 헤더 `x-api-key: secret_value("ARTIFICIAL_ANALYSIS_KEY")`; 키 없으면 `BenchmarkError("config_error")`. 응답 `data`의 지수·가격·속도 숫자 필드를 metric으로(필드명 그대로)
  - JSON·CSV 대신 HTML이 오면 `BenchmarkError("selector_drift")`
  - `service.collect_all(session, fetcher, now) -> dict[str, str]` — 사이트별 결과(`"saved"`·`"unchanged"`·오류 코드). sha256(raw의 정렬된 JSON)이 같으면 저장하지 않음. 한 사이트 예외가 다른 사이트를 막지 않음. 이름은 `resolve_model`로 연결
  - Celery task `benchmarks.collect`, beat `crontab(hour=3, minute=30)`
  - `check_benchmarks(session, *, now) -> list[Finding]` — 사이트별 마지막 스냅샷이 48시간보다 오래되면 `Finding(f"benchmark_stale:{site}", Severity.WARNING, f"{TITLE} 벤치마크가 48시간째 갱신되지 않았습니다")`. 키가 없는 Artificial Analysis는 제외

- [ ] **Step 1: 고정 데이터 저장** — 위 공식 경로를 `curl`로 받아 fixtures에 저장(LMArena는 board 하나, 행 5개로 줄임; Artificial Analysis는 키가 없으면 API 문서의 응답 예시를 저장).
- [ ] **Step 2: 실패하는 테스트 작성**
  - `test_deepswe_rows`: 고정 데이터 첫 행 → metric `pass_at_1`, `ci_low < value < ci_high`, `config == "xhigh"`
  - `test_livebench_picks_newest_available_release`: 날짜 3개 중 최신이 404, 다음이 200이면 그 날짜
  - `test_livebench_columns_become_metrics`: `coding` 열 값이 metric `coding`으로
  - `test_lmarena_pages_until_empty`: 2페이지 응답 → 행 합산, `extra["vote_count"]` 존재
  - `test_artificial_analysis_without_key_is_config_error`
  - `test_html_response_is_drift_and_keeps_last_good`: DeepSWE가 HTML이면 결과 `"selector_drift"`, 기존 DeepSWE 스냅샷 그대로, LiveBench는 `"saved"`
  - `test_unchanged_raw_not_saved`
  - `test_check_benchmarks_stale_after_48h`
- [ ] **Step 3: 실패 확인** — `PYTEST tests/benchmarks -v`. **Step 4: 구현**. **Step 5: 통과 확인**.
- [ ] **Step 6: 커밋** — `feat(benchmarks): DeepSWE, LiveBench, LMArena and Artificial Analysis collectors`

### Task 13: 벤치마크 공개 API와 Opus 입력 연결

**Files:**
- Create: `apps/api/src/news_insight/public/benchmarks.py`
- Modify: `apps/api/src/news_insight/public/routes.py`, `apps/api/src/news_insight/spotlight/service.py`(write가 벤치마크 변화를 입력에 넣음), `apps/api/src/news_insight/cli.py`
- Create: `apps/api/src/news_insight/console/benchmarks.py`(콘솔 라우터, 기존 console 라우터 등록 방식을 따름), `apps/web/app/console/benchmarks/page.tsx`
- Modify: `apps/web/components/console/app-sidebar.tsx`(분석 그룹에 `{ href: "/console/benchmarks", title: "모델 이름 연결" }`)
- Test: `apps/api/tests/public/test_benchmarks_api.py`, `apps/api/tests/console/test_benchmarks.py`, `apps/api/tests/spotlight/test_service.py`(추가)

**Interfaces:**
- Consumes: Task 11·12 모델과 상수
- Produces:
  - `BenchmarkSiteOut(site, title, source_url, license, attribution, release, fetched_at, stale: bool, boards: list[str], rows: list[BenchmarkRowOut])`, `BenchmarkRowOut(board, model, model_id, org, config, metric, value, ci_low, ci_high, extra, rank: int | None, change: Literal["new","up","down","same"] | None, change_by: int)`
  - `benchmarks_view(session, *, now) -> list[BenchmarkSiteOut]` — 사이트별 최신 스냅샷, 순위는 보드·대표 지표(DeepSWE `pass_at_1`, LiveBench 첫 열의 종합값, LMArena `rating`, AA 지능 지수)로 매기고 직전 스냅샷과 비교
  - 라우트 `GET /api/public/benchmarks`
  - `benchmark_changes(session, *, now) -> dict` — `{"changes": [{"site","model","from","to"}], "new_models": [...]}`(대표 지표 Top 20 안의 변화만). CLI `spotlight write`가 이것을 `write(..., benchmarks=...)`로 넘긴다
  - 콘솔 '미매칭 모델'(설계 §7.2): `GET /api/console/benchmarks/unmatched` → `[{model_raw, org, sites, last_seen}]`(model_id가 NULL인 이름), `POST /api/console/benchmarks/aliases {alias, model_name, org}` → `AiModel`이 없으면 만들고 alias 연결 후 기존 점수의 model_id를 채움. 콘솔 화면 `apps/web/app/console/benchmarks/page.tsx`(표 + 이름 입력 연결 폼), 사이드바 '분석' 그룹에 "모델 이름 연결"
- [ ] **Step 1: 실패하는 테스트 작성** — `test_view_marks_stale_after_48h`, `test_rank_change_against_previous_snapshot`, `test_attribution_present_for_artificial_analysis`(`attribution == "Data: Artificial Analysis"`), `test_write_passes_benchmark_changes_to_payload`(가짜 클라이언트가 받은 payload의 `benchmarks.changes` 확인), `test_unmatched_lists_null_model_names`, `test_alias_backfills_existing_scores`(console_client 픽스처).
- [ ] **Step 2: 실패 확인**. **Step 3: 구현**. **Step 4: 통과 확인**.
- [ ] **Step 5: 커밋** — `feat(public): benchmarks endpoint; Opus sees the day's benchmark moves`

### Task 14: AI 모델 탭 — 사이트별 차트·표 재현

**Files:**
- Modify: `apps/web/package.json`(`@tanstack/react-table` 8.x 최신 안정판, 2주 이상 된 버전으로 고정)
- Create: `apps/web/lib/benchmark-types.ts`, `apps/web/components/reader/benchmarks/provider-colors.ts`, `frontier.ts`, `data-table.tsx`, `deepswe.tsx`, `livebench.tsx`, `lmarena.tsx`, `artificial-analysis.tsx`, `models-tab.tsx`
- Modify: `apps/web/app/(reader)/spotlight/page.tsx`, `apps/web/components/reader/spotlight/spotlight-tabs.tsx`(탭 `models` 추가)
- Test: `apps/web/tests/benchmarks.test.tsx`

**Interfaces:**
- Consumes: Task 13 `BenchmarkSiteOut`
- Produces:
  - `providerColor(org: string, theme: "light" | "dark") -> string` — 같은 org는 언제나 같은 색, 알 수 없는 org는 중립 회색. 팔레트는 `card-progress-charts.tsx`의 검증된 단계 색을 이어 쓴다
  - `paretoFrontier(points: {x: number; y: number; id: string}[]) -> string[]` — x(비용) 오름차순으로 y가 지금까지 최대보다 큰 점의 id
  - `<DataTable columns data enableSorting enableColumnVisibility enableExpanding enableRowSelection maxSelected? renderSubRow? />` — TanStack Table 래퍼, shadcn `table.tsx` 마크업, 첫 열 고정·가로 스크롤
  - `<DeepSweChart site />` — Recharts `ScatterChart` + `ErrorBar`(세로 ci) + 효율 경계선 `Line`, 가로축 전환(비용 `mean_cost_usd`·출력 토큰·단계: `extra`의 해당 키), 추론 강도 선택(최고값만·전체), 아래 `DataTable`(모델·pass@1 ±·비용·토큰·단계)
  - `<LiveBenchTable site />` — 종합·영역 열·비용 열, 오픈 웨이트 토글, 조직 선택, 열 선택, 행 펼침(영역 세부), 최대 4개 선택 시 영역별 묶음 막대 비교
  - `<LmArenaTable site />` — 보드 탭, 열: 순위·모델·점수·95% CI(구간 막대: 보드 내 최소~최대 범위에 맞춘 가로 선분)·투표 수·조직·라이선스, 오픈 라이선스 필터, 검색
  - `<ArtificialAnalysisCharts site />` — 지능 지수 가로 막대(상위 20), 지능 대 가격 산점도, 출력 속도 막대, 하단 "Data: Artificial Analysis" 링크. 키 미설정이면 카드에 "키 미설정"
  - `<ModelsTab sites note />` — 상단 Opus `benchmark_note`와 '새로 등장한 모델' 칩, 사이트 카드 4개(각 카드 하단: 갱신일·원본 링크·라이선스/출처, `stale`이면 "갱신 지연" 배지)

- [ ] **Step 1: 의존성 추가** — `PATH=$HOME/.nvm/versions/node/v22.16.0/bin:$PATH npm install @tanstack/react-table@<고정 버전>`(lockfile 포함).
- [ ] **Step 2: 실패하는 테스트 작성**

```tsx
it("keeps provider colours stable", () => {
  expect(providerColor("Anthropic", "light")).toBe(providerColor("anthropic", "light"));
});
it("computes the efficiency frontier", () => {
  expect(paretoFrontier([{id:"a",x:1,y:50},{id:"b",x:2,y:40},{id:"c",x:3,y:70}])).toEqual(["a","c"]);
});
it("sorts the LiveBench table by a clicked column", async () => { /* coding 헤더 클릭 → 첫 행이 coding 최댓값 모델 */ });
it("filters LiveBench to open weights", async () => { /* 토글 → open_weights 아닌 행 사라짐 */ });
it("renders an LMArena interval bar per row", () => { /* 행 수 == role="img" 구간 막대 수 */ });
it("credits Artificial Analysis", () => { /* "Data: Artificial Analysis" 링크 존재 */ });
it("marks a stale site", () => { /* stale=true → "갱신 지연" */ });
```
- [ ] **Step 3: 실패 확인** — `npx vitest run tests/benchmarks.test.tsx`.
- [ ] **Step 4: 구현**.
- [ ] **Step 5: 통과 확인** — 같은 명령, `scripts/dev.sh web-check`.
- [ ] **Step 6: 화면 확인** — 실제 수집 데이터로 AI 모델 탭: 각 사이트 원본 화면과 차트 종류·열 구성이 같은지 나란히 비교, 라이트·다크, 375px.
- [ ] **Step 7: 커밋** — `feat(web): AI 모델 tab recreating each benchmark site's charts and tables`

### Task 15: Part 2 검증과 PR

- [ ] **Step 1:** `scripts/dev.sh verify` 통과.
- [ ] **Step 2:** PR 생성(스크린샷: 사이트별 원본 대 재현 화면), CI 통과. 병합·배포는 사용자 승인 뒤. 배포 후 `docker compose exec -T worker news-insight ...`로 수집 1회 실행해 4곳(키가 없으면 3곳) 저장 확인.
- [ ] **Step 3:** 설계서 상태 줄을 "구현 완료(PR 링크)"로 갱신하고 커밋.
