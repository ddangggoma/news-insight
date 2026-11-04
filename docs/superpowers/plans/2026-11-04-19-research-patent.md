# 연구·특허 — 기술분야별·기업별 추이와 매일의 인사이트

> 요청(2026-11-04): "특허 옆에 연구(논문) 탭이 없습니다. '주목 받는' 탭 뿐 아니라 특허와 논문(신규 생성) 탭을 개선해주세요. 기술분야별, 기업별 정보를 볼 수 있게하고 추이나 인싸이트를 얻을 수 있도록 전면 개편하세요." 이어서 "모든 개발을 진행하세요."
> 상태: **설계 승인(1/4 화면·2/4 데이터는 대화에서 승인, 3/4·4/4는 "모든 개발을 진행하세요"에 따라 확정)**. 배경 보고서: `private-reports/research-patent-insight-plan-2026-11-03.html`(공개 레포 밖). 「오늘」 탭은 「주목 받는」(plan 18)으로 옮겨 갔으므로 여기서는 제외.

## 0. 결정 기록

| # | 질문 | 결정 |
|---|---|---|
| D1 | 1차 범위 | 데이터 보강 + 핵심 화면. 급부상 군집·수명주기 곡선·공백 지도·연구→제품 전이는 2차 |
| D2 | EPO OPS 키 | 나중에. 키 없이 시작, 키가 들어오면 OPS 공보가 자동 합류 |
| D3 | 인사이트 주기 | 매일(05:00 브리핑 뒤, 연구 1회·특허 1회 Opus) |
| D4 | 기업 기준 | 전체 순위 + 관심 기업. 관심 기업 = 기업 레지스트리의 `relation in (self, competitor)`(콘솔에서 이미 편집 가능) |
| D5 | 화면 | 두 메뉴 모두 개요 / 기술분야별 / 기업·기관별 / 추이 / 주목 문헌 |

## 1. 메뉴와 화면

- 독자 메뉴: 「특허」 옆에 「연구」(`/research`)를 새로 두고, 「특허」(`/patents`)를 같은 구조로 다시 만든다. 짧은 모바일 이름: "연구", "특허".
- 공통 탭(`?tab=`): `overview` 개요 · `fields` 기술분야별 · `companies` 기업·기관별 · `trends` 추이 · `documents` 주목 문헌. 공통 기간 선택 `?period=week|month|quarter`(기본 month), 날짜 기준은 KST.
- **개요**: 오늘의 인사이트(Opus, 3~5줄, 근거 문헌 링크) · 핵심 지표 4개(이번 기간 문헌 수와 직전 대비, 급증 분야, 기업 문헌 비중, 관심 기업 문헌 수) · 기술분야×주(최근 12주) 히트맵 · 급증 분야 Top 5.
- **기술분야별**: 12개 분야 칩 → 선택 분야의 테마별 막대(이번 기간 대 직전), 분야 추이 선, 주요 기업·기관 Top 10, 대표 문헌 10건, 분야 한 줄 인사이트(Opus 매일).
- **기업·기관별**: 전체 순위 표(문헌 수, 직전 대비, 주 분야 3개, 관심 기업 표시) + 관심 기업 비교(분야 구성 누적 막대, 기간 추이) + 기업 선택 시 상세(분야 분포, 추이, 최근 문헌). 연구는 기업과 대학·연구기관을 토글.
- **추이**: 분야별 선(상위 8개 + 기타), 연구는 국가별·특허는 공개국별 추이, 급증(z ≥ 2)·급감 표시, 표 보기.
- **주목 문헌**: 연구는 화제 점수(뉴스·커뮤니티 언급, HF 추천, 인용 증가), 특허는 보도 수·관심 기업 여부 순. 분야·기업·기간 필터, 페이지네이션.
- 특허 화면 상단에 데이터 범위 표시: "지식재산 뉴스·EPO 공보 파일럿 기준(공보 수집은 EPO OPS 키 등록 후)".

## 2. 데이터

### 2.1 논문 보강 `research_meta` (1:1 items)
- 열: item_id PK/FK cascade, doi, openalex_id, venue, oa_field, oa_subfield, oa_topic, institutions jsonb [{name, type, country, ror}], countries text[], has_company bool, company_keys text[], cited_by int, fwci float null, counts_by_year jsonb, enriched_at, status(ok|not_found|error), error.
- 대상: research_ip 트랙 중 `item_refs`에 doi 또는 arxiv가 있는 항목(arXiv는 DOI `10.48550/arXiv.<id>`로 조회).
- 수집: OpenAlex 단건 조회 `GET https://api.openalex.org/works/doi:<doi>`(키 헤더는 기존 `provider_headers`), Celery `research.enrich` 매시간 :20, 한 번에 최대 2000건, 최근 항목부터, `not_found`는 7일 뒤 재시도, 기존 레이트 리미터·SafeFetcher 사용. OpenAlex 예산 초과(provider_budget)면 그 회차를 멈추고 다음 회차.
- 기업 연결: 기관 type == "company"인 이름을 `company_aliases`(정규화 표기)로 매칭 → company_keys. 매칭 실패 이름은 집계용 `org_name`으로 남겨 기관 순위에 쓴다.

### 2.2 특허 `patent_meta` (1:1 items)
- 열: item_id, publication_number, kind, office(국가), priority_date null, cpc text[], ipc text[], applicants text[], company_keys text[], source(ops|eps|news).
- 채우기: `patent_office` 소스 항목은 수집 시 저장된 요약(IPC 문자열)과 저자(출원인)에서 파싱, OPS 항목은 같은 필드, ip 카드(뉴스)는 카드의 company_keys와 분야만(source=news). Celery `patents.index` 매시간 :25.
- CPC/IPC → 기술분야 대응표 `apps/api/catalog/cpc_fields.yaml`(주요 서브클래스 → 12개 분야; 예 G06N→ai, G06V→ai, H04W→connectivity, H01M→energy, H10K/G09G→display_av, B25J→robotics_mobility, H01L/H10B→semis, B60W→robotics_mobility, G16H→health_tech, H04L→security/connectivity 등). 매핑이 없으면 카드 분야, 그것도 없으면 "other".

### 2.3 일별 집계
- `research_daily_stats`(day, field, theme, company_key, org_name, country, n) 와 `patent_daily_stats`(day, field, company_key, office, n): 매일 03:40 전날분 재계산 + 최근 2일 갱신, 최초 1회 백필 CLI `news-insight insights backfill-stats`.
- 분야·테마는 카드 분류(ItemCard.field/themes, 앱 공통 12개 분야). 날짜는 coalesce(published_at, first_seen_at)의 KST 날짜.

### 2.4 관심 기업
- `companies.relation in ('self','competitor')`. 콘솔 기업 편집으로 관리(새 테이블 없음).

## 3. 매일의 인사이트 (Opus)

- `news-insight insights write [--kind research|patent] [--date]`: `scripts/dev.sh digest`에서 spotlight write 다음에 실행(실패는 브리핑 상태에 영향 없음, 06·07·08·10시 재시도는 기존 일정 그대로).
- 모델 `insights_model = "claude-opus-5-5"`, 타임아웃 900초, 기존 `ClaudeCli`.
- 입력(종류별): 최근 7일 대 직전 4주 평균의 분야·테마·기업·국가 변화 상위(각 15), 급증 분야, 관심 기업 변화, 분야별 대표 문헌(분야당 5건: did, title_ko, 요약, 기업/기관, 지표).
- 출력 스키마(union 타입 없이): `overview`(3~5문장 배열, 각 문장 `text` + `doc_ids`), `fields`(분야 키 → 한 문장 + doc_ids), `companies`(최대 5: company_key, 한 문장, doc_ids), `watch`(관심 기업 한 문장, 없으면 "").
- 검증: doc_ids가 입력에 있는 것만, 문장 길이 ≤ 200자, 분야 키는 12개 중에서. 저장 `domain_insights`(date, kind, status, model, cost_usd, payload jsonb, generated_at, error), (date, kind) unique, 발행 뒤 불변.
- 화면: 오늘 발행본이 없으면 가장 최근 발행본을 날짜와 함께 보여 준다.
- 운영 알림 `insights_missing:{kind}` 11:00 KST 이후 미발행 시 WARNING.

## 4. API

- `GET /api/public/research?tab=&period=&field=&company=&page=` 와 `GET /api/public/patents?...`(기존 `/patents`는 새 응답으로 교체, 기존 웹 화면도 함께 교체).
- 응답은 탭별 필요한 블록만(개요: kpis, heatmap, risers, insight; fields: fields 목록 + 선택 분야 상세; companies: ranking, watch, detail; trends: series; documents: page). 각 응답 1 MB 미만.

## 5. 테스트와 운영

- pytest: OpenAlex 응답 고정 파일로 파싱·기업 연결·not_found 재시도; IPC 파싱과 CPC→분야; 일별 집계(KST 경계); 각 탭 API; 인사이트 검증·저장·재시도·알림.
- vitest: 탭 전환·기간 선택·분야 칩·기업 표·히트맵·인사이트 근거 링크.
- e2e: 연구 메뉴 열기, 특허 탭 전환.
- 배포 후: `news-insight insights backfill-stats`, 보강 작업 진행률 확인(콘솔 대시보드의 한 줄), 첫 인사이트 수동 1회 실행.

## 6. 단계

P1 데이터(research_meta·보강 작업·기업 연결, patent_meta·CPC 대응, 일별 집계) → P2 API → P3 화면(연구 신설, 특허 교체, 메뉴) → P4 인사이트(Opus)·알림 → P5 검증·배포.
