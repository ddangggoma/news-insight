# 커뮤니티 「화제·속보 신호」 레이어 — 설계

> 요청(2026-11-19, 브레인스토밍 세션에서 결정): 커뮤니티 글을 뉴스와 같은 급으로 다루지 않는다. 커뮤니티는 **무엇이 화제인지(화제)**, **무엇이 뉴스보다 먼저 터졌는지(속보)** 를 알려 주는 신호 레이어로 바꾼다.
> 상태: **구현 PR(병합·배포 전)**. 사용자 부재 중 작성: 가정은 §11에 적었다.
> 관련: Threads 수집 PR ddangggoma/news-insight#156(키워드·프로필 108곳, 좋아요·답글·리포스트·인용 수), 「주목 받는」 설계 [2026-11-03-18-spotlight](../plans/2026-11-03-18-spotlight.md).

---

## 0. 한 장 요약

- **노출 = 신호와 화제 묶음만.** 커뮤니티 글은 탐색 피드·필터 집계·레이더·브리핑 선정에서 빠진다. 뉴스와 커뮤니티를 같은 「건수」로 세지 않는다.
- **카드 = 묶음당 하나.** 커뮤니티 글마다 쓰던 LLM 카드(하루 약 1.2만 장)를 멈추고, 임계값을 넘은 화제 묶음마다 한국어 요약 하나를 쓴다.
- **화제 묶음.** 같은 기사 링크·같은 참조(GitHub·arXiv·CVE·HF)·비슷한 제목(MinHash ≥ 0.6)으로 24시간 안의 커뮤니티 글을 묶고, 작성자 수·플랫폼 수·반응 속도(플랫폼별 z)로 임계값을 판정한다.
- **속보.** 화제 묶음이 임계값을 처음 넘는 순간, 그 이야기를 다룬 뉴스가 아직 하나도 없으면 「속보」. 화면에 표시하고 기존 ntfy/Telegram 채널로 푸시한다(2026-10-05 「알림 없음」 결정을 이 기능에 한해 뒤집음).
- **푸시는 절제.** LLM이 「구체적 사건」이고 「IT 관련」이라 판정한 속보만, 시간당 3건·하루 12건 이하, 00–07시(KST)에는 보내지 않는다. `SIGNAL_PUSH=false`로 끈다(기본 켬).
- **Mastodon 소음 처리.** 하루 50건 넘게 쓰는 봇 11계정이 Mastodon 글의 35 %. 하루 20건 이상 작성자·브리지 계정·봇 표시 계정은 묶음 집계에서 뺀다. 인스턴스가 달라도 페디버스는 한 플랫폼으로 센다.
- **화면.** 독자 메뉴 「화제·속보」(`/buzz`) 신설, 탐색 페이지 맨 위에 속보·화제 3건 띠. 뉴스 목록과 섞지 않는다.

---

## 1. 현재 상태 (2026-11-19 라이브 실측, 24시간)

| 항목 | 값 |
|---|---|
| 커뮤니티 글 | 약 1.18만 건(Mastodon 7,992 · DEV 1,336 · HN 512 · Fosstodon 391 · V2EX 346 · Bluesky 186 …) |
| 커뮤니티 카드 생성 | 1.2만 장/일 — 전체 카드 부담의 대부분 |
| 기사 링크가 있는 글 | 7,367건(62 %) — 가장 강한 묶음 열쇠 |
| Mastodon 작성자 분포 | 50건+ 11명이 2,852건(35 %), 20–49건 31명이 940건. `EUVD_Bot`, `thehackerwire`, `*@web.brid.gy`(뉴스 사이트 브리지) 등 |
| Mastodon 중복(다른 인스턴스·해시태그) | 3,368건이 이미 `item_dedup.duplicate_of` |

커뮤니티가 뉴스와 같은 급으로 쓰이던 곳:

- `briefing/selection.py` — `track_min.community = 8`, `track_gate_min.community = 3`(게이트까지 걸려 있음)
- `public/filters.py`·`public/facts.py` — 탐색 피드·패싯·인사이트·레이더가 카드가 있는 모든 트랙을 같은 건수로 셈
- `public/signals.py` — `hype` 규칙이 「뉴스+커뮤니티」 합계
- `cards/service.py` — 커뮤니티 글에도 글마다 LLM 카드, 중복 글에는 카드 복사(`reuse_cards`)
- `stories/service.py` — 카드가 생긴 커뮤니티 글이 스토리에 붙어 `source_count`(출처 수)를 부풀림

---

## 2. 결정

| # | 질문 | 결정 |
|---|---|---|
| D1 | 커뮤니티 노출 | 신호와 화제 묶음만. 글 단위로 뉴스 목록에 나오지 않음 |
| D2 | 카드 | 묶음당 하나(임계값 이상). 글 단위 LLM 카드 중단 |
| D3 | 속보 | 화면 + 푸시(ntfy/Telegram). 2026-10-05 「알림 없음」을 이 기능에 한해 뒤집음 |
| D4 | 푸시 스위치 | `SIGNAL_PUSH`(기본 켬), 시간당·일 상한, 00–07시 KST 무음 |
| D5 | 「주목 받는」 커뮤니티 탭 | 그대로 둠(전용 탭이라 뉴스와 섞이지 않음). 카드가 없어지면 원제목으로 표시됨 — §10 후속 |

---

## 3. 뉴스와 커뮤니티를 같은 건수로 세지 않기

1. **브리핑 선정**: `SelectionRules.track_min`·`track_gate_min`에서 `community` 삭제, `eligible_items`가 커뮤니티 트랙을 제외. 60건은 뉴스·연구·오픈소스로 채운다(뉴스 최소 30 → 그대로, 남는 8자리는 점수순).
2. **독자 목록·집계**: `ReaderFilters.conditions()`와 reader facts 조건에 `track <> 'community'`. 피드·패싯·인사이트·레이더가 한 번에 바뀐다. `track=community` 필터 값은 오래된 링크가 400이 되지 않도록 허용은 하되 결과가 비게 된다.
3. **레이더 hype 규칙**: 「뉴스+커뮤니티」 → 「뉴스」만. 문구도 「뉴스 N건」. 커뮤니티의 열기는 화제 묶음이 따로 보인다.
4. **카드 큐**: `pending_condition`·`classify_pending_condition`·`reuse_cards`가 커뮤니티를 건너뛴다(`COMMUNITY_ITEM_CARDS=false`, 기본). 카드가 없으니 새 커뮤니티 글은 스토리에도 붙지 않아 뉴스 `source_count`가 더는 부풀지 않는다.
5. 기존 커뮤니티 카드·스토리 소속은 지우지 않는다(되돌리기 쉬움). 읽기 쪽 조건이 이미 걸러 낸다.

---

## 4. 화제 묶음(`buzz_clusters`)

### 4.1 대상 글

- 트랙 `community`, 카나리 아님, 처음 본 지 24시간 이내(`WINDOW`).
- 다른 글의 반복(`item_dedup.duplicate_of`)은 제외. 단 **기사를 공유한 글**(`matched_by = 'link'`)은 커뮤니티 자신의 반응이므로 포함(스포트라이트 R6과 같은 규칙).

### 4.2 글마다 한 번 계산하는 열쇠(`buzz_item_keys`)

10분마다 새 글에만 계산해 저장한다(1.2만 건 MinHash를 매번 다시 계산하면 13초).

| 열쇠 | 내용 |
|---|---|
| `link_key` | 글이 공유한 기사의 URL 키(`item_dedup.link_key`) |
| `refs` | 제목·요약·URL의 GitHub 저장소, arXiv, DOI, CVE, HF 모델(`stories/refs.py`) |
| `signature`·`bands` | URL·해시태그·멘션을 뺀 제목의 MinHash(64)와 LSH 밴드(16) |
| `platform` | 운영 주체를 플랫폼 계열로 묶음: Mastodon gGmbH·Fosstodon·mstdn.jp → `fediverse`, HN 두 경로 → `hn`, V2EX 노드 → `v2ex`, Meta Platforms → `threads` |
| `author` | `platform:작성자`(소문자) |

### 4.3 묶기

24시간 창의 글을 union-find로 잇는다.

- 같은 `link_key` → 한 묶음
- 같은 참조(`kind:value`) → 한 묶음
- 같은 LSH 밴드를 공유하고 **서명 유사도 ≥ 0.6** → 한 묶음(스토리의 0.45보다 엄격: 짧고 시끄러운 글이 많음)

글이 2건 이상인 성분만 묶음으로 저장한다. 이전 실행의 묶음 id는 구성원 다수결로 이어받고(동률이면 오래된 쪽), 둘 이상이 한 성분이 되면 작은 쪽을 큰 쪽에 합친다(`merged_into`).

### 4.4 소음 제거(집계에서 빼는 글)

- 같은 플랫폼에서 24시간에 **20건 이상** 쓴 작성자(봇·피드 계정)
- 작성자 이름에 `bot`이 단어로 들어가거나 `@web.brid.gy`·`@rss-parrot`·`@newsmast` 같은 브리지 계정
- 작성자 없음
- 같은 작성자의 글은 묶음 안에서 한 명으로 셈

빠진 글도 묶음 구성원으로는 남는다(링크를 이어 주는 역할). 임계값과 순위에는 쓰지 않는다.

### 4.5 열기(heat)

스포트라이트의 플랫폼 정규화(`spotlight/scoring.py`)를 그대로 쓴다. 글마다 최신 지표 스냅샷 → 시간당 속도 `log1p(반응/경과시간)` → 플랫폼 안 z. 묶음의 열기 = 사람 글 z의 양수 합. Threads는 `likes + replies + reposts + quotes`로 추가(PR #156의 운영 주체 `Meta Platforms`).

### 4.6 임계값

| 판정 | 조건 |
|---|---|
| **화제** | (작성자 ≥ 3 **그리고** 플랫폼 ≥ 2 **그리고** 열기 ≥ 1.5) **또는** (작성자 ≥ 5 **그리고** 열기 ≥ 3.0) |
| 점수(순위) | `10·플랫폼 + 4·min(작성자, 20) + 5·열기` |

한 번 넘은 묶음은 `crossed_at`을 남기고, 마지막 글 이후 24시간 동안 화면에 남는다.

근거: 하루 사람 글 약 7천 건 중 한 기사를 서로 다른 플랫폼의 3명이 공유하는 경우는 드물다(링크 공유 글의 대부분은 한 플랫폼 한 명). 열기 1.5는 「플랫폼 평균보다 1σ 위인 글 한두 건」 수준. 작성자 5명·열기 3.0은 HN·Threads 한 곳에서만 터진 경우를 받기 위한 경로.

### 4.7 뉴스와 잇기

임계값을 넘은 묶음만(하루 수십 건) 뉴스와 대조한다. 대상: 뉴스 트랙, 처음 본 시각이 묶음 첫 글 48시간 전 이후.

1. 묶음 글의 `link_key` = 뉴스 글의 `url_key` (기사를 직접 공유)
2. 같은 참조(`item_refs`)
3. 대표 글 제목과 뉴스 원제목의 pg_trgm 유사도 ≥ 0.5, 또는 묶음 한국어 제목과 뉴스 한국어 카드 제목 ≥ 0.5

잇힌 뉴스는 최대 10건 저장(`news_item_ids`), 가장 이른 뉴스 시각을 `news_first_seen_at`으로 둔다.

---

## 5. 묶음 요약(카드 대신)

- 호스트 카드 실행(10분, `scripts/dev.sh cards`) 끝에 `news-insight buzz summarize`.
- 대상: 화제 판정 묶음 중 요약이 없거나, 마지막 요약 뒤 사람 글이 1.5배 이상 늘어난 묶음(최대 3회). 실행당 최대 12묶음, 한 번의 호출.
- 엔진: 카드와 같은 사슬(Antigravity → agy Claude → Claude Code Sonnet)의 `ask(prompt, schema)`. 실패는 시도 횟수만 늘림(3회까지).
- 입력: 묶음마다 사람 글 최대 12건의 원문 제목·플랫폼·반응, 잇힌 뉴스 제목.
- 출력: `title_ko`(40자 이내), `summary_ko`(1–3줄), `keywords`(5개 이내), `is_event`(출시·장애·취약점·발표·인수 같은 구체적 사건인지, 의견·토론·밈이 아닌지), `relevant`(IT·DX 관련인지).
- 입력 안 지시문은 데이터로만 다룬다(기존 카드 시스템 문구와 동일).

---

## 6. 속보

- **판정 시점**: 묶음이 처음 화제 임계값을 넘는 실행.
- **조건**: 그 시점에 잇힌 뉴스가 하나도 없고(`news_first_seen_at`이 없거나 지금보다 뒤), 묶음 첫 글이 6시간 이내.
- **뉴스 따라잡기**: 이후 실행에서 뉴스가 잇히면 `news_caught_up_at`. 화면에 「뉴스보다 N분 먼저」를 보인다. 속보 표시는 그대로 둔다(먼저 터졌다는 사실은 변하지 않음).
- **푸시 조건**: 속보 + 요약 완료 + `is_event` + `relevant` + 속보 판정 후 3시간 이내 + 아직 안 보냄.
- **채널**: 워치독과 같은 환경변수(`WATCHDOG_NTFY_TOPIC`·`_SERVER`·`_TOKEN`, `WATCHDOG_TELEGRAM_BOT_TOKEN`·`_CHAT_ID`)를 앱 컨테이너에도 넘긴다. `SIGNAL_NTFY_TOPIC` 등으로 따로 지정 가능.
- **절제**: 시간당 3건, 하루(KST) 12건, 00:00–07:00 KST 보내지 않음. 무음 시간에 판정된 속보는 07시에 3시간 이내인 것만 보낸다. 보낸 시각·채널은 `pushed_at`·`push_channels`에 남겨 한 번만 보낸다. 채널 하나가 실패해도 다른 채널은 보낸다.
- **스위치**: `SIGNAL_PUSH=false`면 판정·화면은 그대로, 푸시만 멈춘다.
- **푸시 문구**: 제목 `[속보] {title_ko}`, 본문 요약 1–2줄 + `플랫폼 N곳·작성자 N명` + 링크(`{PUBLIC_BASE_URL}/buzz#c{id}`).

---

## 7. 작업 흐름

| 무엇 | 어디서 | 주기 |
|---|---|---|
| `buzz.update`: 열쇠 계산 → 묶기 → 집계·임계값 → 뉴스 잇기 → 속보 판정 → 푸시 | Celery(컨테이너) | 10분 |
| `buzz summarize`: 묶음 요약 | 호스트 카드 실행 끝 | 10분 |
| 오래된 열쇠 정리(3일) | `buzz.update` 안 | 10분 |

푸시는 요약이 필요하므로 보통 판정 후 10–20분 안에 나간다.

---

## 8. 데이터 모델(마이그레이션 0052, 추가만)

- `buzz_item_keys(item_id PK, platform, author, link_key, refs jsonb, signature bigint[], bands bigint[], first_seen_at, computed_at)`
- `buzz_clusters(id, first_seen_at, last_seen_at, post_count, human_posts, author_count, platform_count, platforms jsonb, heat, score, lead_item_id, crossed_at, breaking, breaking_at, news_item_ids jsonb, news_first_seen_at, news_caught_up_at, title_ko, summary_ko jsonb, keywords jsonb, is_event, relevant, summary_engine, summary_model, summarized_at, summary_posts, summary_attempts, summary_error, pushed_at, push_channels jsonb, merged_into, updated_at)`
- `buzz_cluster_items(item_id PK, cluster_id, relation, joined_at)`

이전 코드는 새 표를 읽지 않으므로 되돌리기 안전하다.

---

## 9. 화면

- **「화제·속보」 메뉴(`/buzz`)**: 「주목 받는」 다음 자리. 속보(빨간 표시, 「뉴스보다 N분 먼저」 또는 「아직 뉴스 없음」), 화제 순서. 묶음마다 한국어 제목·요약(없으면 대표 원문 제목), 플랫폼·작성자·열기, 대표 글 5건 링크, 잇힌 뉴스 링크.
- **탐색 페이지 띠**: 다이제스트 배너 아래 한 줄 띠에 속보 우선 3건 + 「화제·속보 전체」 링크. 피드 목록과 분리.
- API: `GET /api/public/buzz?hours=24` → `{generated_at, clusters: [...]}`.

---

## 10. 범위 밖·후속

- 「주목 받는」 커뮤니티 탭을 화제 묶음으로 바꾸기(지금은 원제목으로 남음).
- 다국어 묶기(bge-m3 임베딩): 지금은 같은 언어 제목·링크·참조만 묶는다.
- 묶음에 기술 분류(themes)를 달아 레이더 hype에 다시 커뮤니티 열기를 넣기.
- 기존 커뮤니티 카드·스토리 소속 정리(되돌리기 위해 이번에는 남김).
- 콘솔에 묶음 품질 점검 화면.

---

## 11. 가정(사용자 부재 중)

1. 임계값(§4.6)·소음 규칙(§4.4)은 11-19 하루 실측으로 정했다. 라이브 2–3일 관찰 뒤 조정을 권한다.
2. 푸시 채널은 워치독과 같은 ntfy 토픽·Telegram 대화방을 쓴다(따로 두려면 `SIGNAL_*` 변수).
3. 「주목 받는」 커뮤니티 탭은 이번에 손대지 않는다.
4. 기존 커뮤니티 카드는 지우지 않고 읽기에서만 뺀다.
5. 마이그레이션 번호는 0052(PR #155가 0051을 씀). 병합 순서에 따라 `down_revision`을 맞춘다.
