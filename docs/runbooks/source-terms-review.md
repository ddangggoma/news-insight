# 런북: 소스 이용약관 검토와 V1 통과시키기

> **목적:** 카탈로그에 등록한 소스가 V1(정책/약관 검토)을 통과하도록 약관 정보를 기록하고, V2·V3을 거쳐 수집과 24시간 Canary(V4)까지 진행합니다.
> **대상 파일:** `apps/api/catalog/sources.yaml`
> **소요 시간:** 소스 1개당 약 5~15분 (약관을 읽는 시간 포함)

> ⚠️ 이 문서는 운영 절차 안내이고 법률 자문이 아닙니다. 약관이 모호하면 가장 보수적인 등급(`metadata_only`)을 고르고, 상업적으로 이용하기 전에는 법무 검토를 받으세요.

---

## 전체 흐름

```
① 약관 찾기 → ② 저장 등급 판단 → ③ 카탈로그에 기록 → ④ seed → ⑤ validate (V0~V3)
   → ⑥ 수집 시작 (Phase 2 완료 후 자동) → ⑦ 24시간 뒤 sources canary (V4)
```

| 단계 | 누가 하나 | 언제 가능한가 |
|---|---|---|
| ①~⑤ 약관 기록과 V0~V3 검증 | 운영자 (직접) | **지금 바로** |
| ⑥ 자동 수집 | 시스템 | Phase 2 개발이 끝난 뒤 |
| ⑦ V4 판정 | 운영자가 명령 1회 실행 (또는 1시간마다 자동) | 수집 시작 후 24시간 이상 지난 뒤 |

---

## V1이 확인하는 항목

V1 검사(`check_policy`)는 아래 항목이 **모두** 충족되어야 통과합니다.

| 항목 | 조건 | 해당 소스 |
|---|---|---|
| `terms_url` | 이용약관 또는 이용조건 페이지 주소가 있어야 하고, `https://`로 시작해야 함 | 전체 |
| `storage_right` | 원문 저장 등급 4가지 중 하나가 명시되어 있어야 함 | 전체 |
| `config.crawl_permitted: true` | 약관상 자동 수집(크롤링)이 허용된다고 확인했음 | `access_method: crawler`만 |
| `config.robots_checked: true` | `robots.txt`를 확인했고 수집 경로가 막혀 있지 않음 | `access_method: crawler`만 |
| `config.selectors` | 목록·제목·링크 선택자를 정의했음 | `access_method: crawler`만 |
| `config.open_access: true` | 오픈 액세스(무료 공개)임을 확인했음 | 연구·특허 트랙에서 전문 저장 등급을 고를 때만 |

> 시드 소스 10개는 지금 모두 `feed`, `atproto`, `research_api`, `github` 방식이라 **크롤러 항목은 해당 없습니다.** 지금은 `terms_url`과 `storage_right`만 채우면 됩니다.

---

## Step 1. 약관 페이지 찾기

소스마다 아래 순서로 찾습니다.

1. **사이트 맨 아래(푸터)를 봅니다.**
   "Terms of Use", "Terms of Service", "Legal", "이용약관", "저작권 정책", "利用規約" 같은 링크를 찾습니다.
2. **RSS나 API 전용 안내 페이지가 있는지 확인합니다.**
   일부 언론사는 "RSS 서비스 안내"나 "RSS 이용 조건" 페이지를 따로 둡니다. API는 개발자 문서에 "Terms", "License", "Usage policy"가 있습니다. **전용 안내가 있으면 일반 약관보다 이쪽을 우선합니다.**
3. **찾은 페이지에서 아래 질문의 답을 확인합니다.**
   - 자동으로 가져가는 것(RSS 구독, API 호출)을 허용하는가?
   - 제목·링크만 써도 되는가, 요약(발췌)까지 보여줘도 되는가?
   - 본문 전체를 저장해도 되는가? 된다면 기간 제한이 있는가?
   - 상업적 이용을 금지하는가?
   - 출처 표시 의무가 있는가?
4. **주소를 복사합니다.** `https://`로 시작하는 최종 주소여야 합니다. 리다이렉트된 뒤의 주소를 쓰세요.

### 시드 소스별로 찾아볼 곳

| key | 운영 주체 | 찾아볼 곳 (힌트) |
|---|---|---|
| `the-verge` | Vox Media | theverge.com 푸터의 Terms of Use (Vox Media 공통 약관) |
| `ars-technica` | Condé Nast | arstechnica.com 푸터의 User Agreement / Terms (Condé Nast 공통) |
| `etnews` | 전자신문사 | etnews.com 하단 이용약관·저작권 안내, RSS 서비스 안내 페이지 |
| `itmedia-news` | ITmedia Inc. | itmedia.co.jp 하단 利用規約, RSS 이용 안내 |
| `google-blog` | Google LLC | Google 서비스 약관(policies.google.com/terms 계열) |
| `hacker-news` | Y Combinator | news.ycombinator.com 하단 Legal / Guidelines, HN API 문서 |
| `bluesky-official` | Bluesky Social PBC | bsky.social / bsky.app의 Terms of Service, AT Protocol 개발자 정책 |
| `arxiv-cs-ai` | Cornell University | arXiv의 이용 조건 페이지, arXiv API Terms of Use (메타데이터 라이선스 안내 포함) |
| `openalex-works` | OurResearch | OpenAlex 문서의 License 안내 (데이터 라이선스) |
| `github-on-device-ai` | GitHub, Inc. | GitHub Terms of Service, GitHub API 이용 정책 |

> 위 표는 찾아볼 위치를 알려주는 힌트입니다. 실제 주소와 내용은 직접 열어서 확인하세요. 약관은 수시로 바뀝니다.

---

## Step 2. 원문 저장 등급 고르기

약관을 읽고 아래 표에서 **조건을 만족하는 가장 낮은 등급**을 고릅니다. 애매하면 한 단계 낮춥니다.

| 등급 | 시스템이 저장하는 것 | 이럴 때 선택 |
|---|---|---|
| `metadata_only` | 제목, URL, 발행일, 저자만 | 약관이 전재·복제를 금지하거나, 허용 범위가 불명확할 때 (**기본 선택**) |
| `excerpt_allowed` | 위 항목 + 요약 최대 500자 | 피드가 제공하는 요약을 출처 링크와 함께 보여주는 것이 허용되거나 관행상 명백할 때 |
| `fulltext_ttl` | 위 항목 + 전문 (30일 뒤 자동 삭제) | 전문을 일시적으로 저장·처리하는 것은 허용되지만, 영구 보관 근거는 없을 때 |
| `fulltext_permitted` | 위 항목 + 전문 영구 보관 | CC BY, CC0 같은 오픈 라이선스이거나 약관이 전문 저장을 명시적으로 허용할 때 |

**판단 팁**
- 언론사 RSS는 대부분 "개인적·비상업적 구독용"으로 제공됩니다. 이 서비스는 요약을 재가공해서 브리핑을 발행하므로, 명시적 허락이 없으면 `metadata_only`가 안전합니다.
- 연구·특허 트랙(`research_ip`)에서 `fulltext_*`를 고르면 `config.open_access: true`도 함께 적어야 V1을 통과합니다. 페이월(유료 구독) 뒤의 논문 전문은 절대 수집하지 않습니다.
- 등급은 나중에 바꿀 수 있습니다. 바꿔도 검증이 초기화되지 않습니다 (Step 5 참고).

---

## Step 3. 카탈로그에 기록하기

`apps/api/catalog/sources.yaml`에서 해당 소스의 `terms_url`, `storage_right`를 채웁니다. 검토 근거를 남기기 위해 `config`에 검토일과 메모도 적어 두는 것을 권장합니다. 이 두 키는 검증 로직이 쓰지는 않고 기록용입니다.

**수정 전**

```yaml
  - key: hacker-news
    name: Hacker News Front Page
    track: community
    ...
    dx_relevance: 개발자 커뮤니티의 기술 화제와 오픈소스 반응 신호
    storage_right: metadata_only
```

**수정 후 (예시)**

```yaml
  - key: hacker-news
    name: Hacker News Front Page
    track: community
    ...
    dx_relevance: 개발자 커뮤니티의 기술 화제와 오픈소스 반응 신호
    terms_url: https://<확인한 약관 주소>
    storage_right: metadata_only
    config:
      terms_reviewed_at: "2026-10-03"
      terms_note: "RSS 공개 제공, 전재 허용 조항 없음 → 메타데이터만"
```

**작성 규칙**
- `terms_url`은 반드시 `https://`로 시작해야 합니다. `http://`면 V1에서 실패합니다.
- 들여쓰기는 스페이스 4칸(항목 안), 탭 문자는 쓰지 않습니다.
- 이미 `config:`가 있는 소스(`bluesky-official`, `arxiv-cs-ai`, `openalex-works`, `github-on-device-ai`)는 **기존 키를 지우지 말고** 아래에 추가합니다.
- 오타가 있으면 다음 단계의 `seed`가 오류를 내며 어느 필드가 틀렸는지 알려줍니다.

---

## Step 4. 카탈로그를 DB에 반영하기 (seed)

```bash
cd /Users/ggoma/WorkSpace/NEWS_INSIGHT
scripts/dev.sh db
cd apps/api
uv run alembic upgrade head
uv run news-insight sources seed
```

**예상 출력**

```
created=0 updated=1 reset=0
```

- `updated`는 약관 정보를 채운 소스 수입니다.
- `reset`이 0보다 크면 `endpoint_url`, `official_domain`, `access_method` 중 하나가 바뀐 것입니다. 해당 소스는 검증을 처음부터 다시 해야 합니다. 의도한 변경이 아니면 YAML을 되돌리세요.
- 오류가 나면 메시지에 나온 필드(예: `terms_url`, `storage_right`)의 값을 확인합니다.

---

## Step 5. 검증 사다리 올리기 (V0 → V3)

```bash
uv run news-insight sources validate hacker-news
```

**예상 출력 (정상)**

```
V1 passed: ok
V2 passed: ok
V3 passed: ok
hacker-news: stage=V3 status=candidate
```

(이미 V0를 통과한 소스는 V1부터 시작합니다.)

**결과가 다를 때**

| 출력 | 의미 | 조치 |
|---|---|---|
| `V1 failed: terms_url is missing` | 약관 주소가 비어 있음 | Step 3 다시 확인 후 `seed` 재실행 |
| `V1 failed: terms_url must use https` | `http://` 주소 | `https://` 주소로 교체 |
| `V1 failed: ... paywall bypass is forbidden` | 연구 트랙에서 전문 등급을 골랐는데 `open_access` 표시가 없음 | 오픈 액세스가 맞으면 `config.open_access: true` 추가, 아니면 등급을 낮춤 |
| `V2 failed: refusing non-public address ...` | 주소가 사설 IP로 해석됨 | 엔드포인트 주소를 확인 (정상 공개 사이트라면 발생하지 않음) |
| `V2 failed: unexpected content type ...` | RSS가 아닌 HTML 페이지를 받음 | 피드 주소가 바뀌었는지 사이트에서 확인 후 `endpoint_url` 수정 (검증 초기화됨) |
| `V3 failed: only N recent complete items (need 3)` | 최근 30일 안의 완전한 항목이 3개 미만 | 피드가 살아 있는지 확인. 업데이트가 드문 소스는 `config.probe_max_age_days`를 늘림 |
| `V3 failed: feed could not be parsed: no entries` | 피드가 비어 있음 | **arXiv는 토·일요일에 항목이 0개입니다.** 평일에 다시 실행 |
| `V3 failed: no V3 parser probe for access method '...' yet` | JSON API 방식(Bluesky, OpenAlex, GitHub) | 정상입니다. Phase 3에서 V3 검사가 추가되기 전까지 V2에서 대기 |

**한 번에 상태 보기**

```bash
uv run news-insight sources report
```

맨 아래 `Validation stages`에서 `V3` 숫자가 늘었는지 확인합니다.

---

## Step 6. 수집 시작 (Phase 2 완료 후)

Phase 2 개발이 끝나면 **V3 이상인 후보 소스는 자동으로 Canary 모드 수집**이 시작됩니다. 이렇게 모은 데이터는 V6가 되기 전까지 발행에 쓰이지 않습니다.

```bash
cd /Users/ggoma/WorkSpace/NEWS_INSIGHT
scripts/dev.sh up                                 # 전체 스택 실행 (worker, scheduler 포함)
cd apps/api
uv run news-insight collect run hacker-news       # 즉시 1회 수집해서 동작 확인
uv run news-insight collect status                # 다음 수집 시각, 주기, 연속 실패 수
```

- `collect run` 결과가 `success http=200 new=...`이면 정상입니다.
- 이후에는 Celery Beat가 1분마다 기한이 된 소스를 자동으로 수집합니다. Mac이 잠자기에 들어가면 수집이 멈추므로, 24시간 동안 켜 두세요.

---

## Step 7. 24시간 뒤 V4 판정

V3 통과 시점부터 **24시간 이상, 4회 이상** 수집 기록이 쌓이면 판정할 수 있습니다. 시스템이 1시간마다 자동으로 판정하고, 직접 실행할 수도 있습니다.

```bash
uv run news-insight sources canary
```

**예상 출력**

```
hacker-news: V4 passed: ok
```

**판정 기준** (하나라도 넘으면 실패)

| 지표 | 기준 |
|---|---|
| 오류율 (실패 + Dead Letter) | 10% 이하 |
| HTTP 429 비율 | 5% 이하 |
| 응답 시간 p95 | 10초 이하 |
| 중복 URL 비율 | 20% 이하 |

- 실패하면 사유가 함께 출력되고, **그 시점부터 24시간 관찰을 다시 시작**합니다.
- 아직 24시간이 안 됐으면 `no sources ready for V4 yet`이 나옵니다. 정상입니다.
- V5(7일 품질 시험)와 V6(정식 편입)는 Phase 5에서 자동화됩니다 (로드맵 D8).

---

## 문제가 생겼을 때

| 상황 | 명령 |
|---|---|
| 수집 실패가 쌓였는지 확인 | `uv run news-insight dlq list` |
| 원인을 고친 뒤 즉시 재수집 | `uv run news-insight dlq retry <id>` |
| 사이트 구조 변경(selector drift)으로 자동 일시정지된 소스 재개 | `uv run news-insight sources resume <key>` |
| 약관 문제 등으로 수집을 직접 멈춤 | `uv run news-insight sources pause <key> --reason "사유"` |

---

## 체크리스트 (소스 1개당)

- [ ] 약관 또는 RSS·API 이용조건 페이지를 찾아 읽었다
- [ ] 자동 수집 허용 여부, 발췌·전문 저장 허용 범위, 상업적 이용 제한을 확인했다
- [ ] `terms_url`(https)과 `storage_right`를 기록했다
- [ ] `config.terms_reviewed_at`, `config.terms_note`에 검토 근거를 남겼다
- [ ] `sources seed` → `updated` 확인
- [ ] `sources validate <key>` → `stage=V3` 확인 (JSON API 방식은 V2까지)
- [ ] (Phase 2 완료 후) 24시간 수집 → `sources canary` → `V4 passed`
