# 웹 리디자인 & 기간별 인사이트 분석 — 계획안

> **상태:** R1 완료, R2는 P4로 대체, R4 구현 중(B+C).
> **시안 페이지:** https://claude.ai/artifact/7PDUTUyp4HVMQZ1dVMzVLo (데스크톱·태블릿·모바일 폭 전환, 예시 데이터)
> **HTML 시안 (예시 데이터, 브라우저로 바로 열기):** [`docs/design/mockups/mockup-a-briefing.html`](../../design/mockups/mockup-a-briefing.html), [`mockup-b-explore.html`](../../design/mockups/mockup-b-explore.html), [`mockup-c-radar.html`](../../design/mockups/mockup-c-radar.html)
> **분류 선택 위자드:** https://claude.ai/artifact/3fEunMiBCX6wjmSJkHLMP9
> **관련 로드맵:** P4(분류), P7(전략 보고서), P8(독자 웹) — [`2026-10-03-00-roadmap.md`](2026-10-03-00-roadmap.md)

## 0. 확정한 방향 (2026-10-04)

| 항목 | 결정 |
|---|---|
| 적용 범위 | 독자용 인사이트 웹 신설 + 현 콘솔은 관리 영역(`/admin`)으로 분리, 같은 디자인 시스템 |
| 탐색 축 | 기술 분야 15 × 제품군 11 (2축), 보조 축은 트랙·지역·영향(기회·위험·관찰) |
| 분석 주기 | 일간·주간·월간·분기 리포트와 롤업 지표 |
| 기준 화면 | 데스크톱 우선, 모바일은 탭·시트로 접기 |
| 공개 범위 | 독자 웹은 로그인 없이 공개 (관리 영역만 보호) |
| 리포트 생성 | 주·월·분기 리포트도 호스트 Claude CLI로 작성 (성능 우선) |
| 착수 | R1(토큰)과 R2(분류)를 병렬 진행 |

## 1. 현황 진단

| 문제 | 근거 | 개선 방향 |
|---|---|---|
| 기술·제품 분류가 데이터에 없음 | `apps/web/lib/format.ts` `CATEGORY_LABEL`은 출처 유형(독립 언론, 개발자 포럼 등) | 카드 생성 단계에서 분야·제품군·영향 부여 |
| 기간 단위 분석 없음 | 카드·지표 화면은 "최근 1·3·7·30일" 필터뿐 | 일 롤업 → 주/월/분기 집계, 기간 리포트 |
| 독자 화면 없음 | `apps/web/app/page.tsx`는 안내 문구 한 줄 | `/`를 독자용 홈으로 |
| 운영·열람 메뉴 혼재 | `components/console/app-sidebar.tsx` | 독자 내비와 관리 내비 분리 |
| 본문이 회색, 위계 평평 | `components/console/news-card.tsx` 요약에 `text-muted-foreground`, 동일 크기 카드 4열 | 본문 대비 7:1 이상, 리드·목록 위계 |
| 분류 색 체계 없음 | `components/console/badges.tsx` TrackBadge 모두 `secondary` | 트랙 4색, 영향 3색 시맨틱 토큰 |
| 한국어 줄바꿈 미처리 | `app/globals.css`에 `word-break: keep-all` 없음 | `keep-all` + `text-wrap: balance/pretty` |
| 키워드가 자유 텍스트 | `item_cards.keywords` JSONB, 엔진(Antigravity·Qwen)마다 표기 다름 | 정규 키워드 사전 + 별칭 테이블 |

## 2. 디자인 시스템

스택(Next.js 16, Tailwind v4, shadcn/Radix, Pretendard)은 유지하고 토큰과 규칙만 교체합니다.

**가독성 규칙**
- 본문 16px / 행간 1.7–1.8, 한 줄 60–70자. 표·목록 같은 밀집 화면만 14px
- 본문 대비 7:1 이상, 보조 텍스트 4.5:1 이상. 요약을 muted 회색으로 두지 않음
- `word-break: keep-all`, 제목 `text-wrap: balance`, 본문 `text-wrap: pretty`
- 숫자는 `tabular-nums`
- 색은 의미에만: 강조색 1 + 트랙 4색 + 영향 3색(기회=녹색, 위험=적색, 관찰=중립)
- 라이트·다크 동일 품질, `focus-visible` 링, `prefers-reduced-motion` 존중

**타입 스케일:** 28/700 헤드라인 · 20/700 섹션 · 16/600 기사 제목 · 16/400 본문 · 13/500 메타 · mono 12 수치

**최신 CSS·컴포넌트 검토**

| 기술 | 쓰임 | 판단 |
|---|---|---|
| Container Queries | 패널 폭 기준 재배치 (사이드바 접힘에도 대응) | 채택 |
| `:has()` | 선택된 필터·빈 상태 스타일 | 채택 |
| Subgrid | 카드 그리드의 제목·요약·출처 줄맞춤 | 채택 |
| oklch · `color-mix()` | 다크 토큰, 히트맵 단계색 (보간은 `in oklab`로 색상 왜곡 방지) | 채택 |
| `text-wrap: balance/pretty` | 한국어 제목 줄바꿈 | 채택 |
| `content-visibility: auto` | 긴 피드 렌더 비용 | 채택 |
| View Transitions | 목록→상세, 기간 탭 전환 | 점진 적용 |
| Popover API · Anchor Positioning | 키워드 툴팁, 근거 미리보기 | 보류 (Radix Popover 유지) |
| Web Components (Lit 등) | 외부 사이트 임베드 위젯 | 보류 (React 19 + Radix라 이점 적음) |

## 3. 정보 구조

```
/                          오늘 브리핑 (일간 다이제스트 확장)
/brief/week/2026-W40       주간 리포트 · ISO 주, 월요일 시작, KST
/brief/month/2026-09       월간 리포트
/brief/quarter/2026-Q3     분기 리포트
/explore?field=&product=&track=&region=&impact=&period=   패싯 탐색
/topics/[field]            기술 분야 페이지
/products/[product]        제품군 페이지
/keywords/[keyword]        키워드 페이지 (수명주기·동시출현·지역 확산)
/items/[id]                기사 상세
/search?q=                 전체 검색 (pg_trgm)
/admin/*                   현 /console 이전
```

> **변경 (2026-10-04):** 아래 위자드 분류(R2)는 `main`에 먼저 합쳐진 P4 분류(분야 15·테마 75·DX 사업부 6·영향·범위·관련도, `taxonomy/catalog.py`)와 같은 카드 호출을 두고 겹쳐서 되돌렸습니다. 독자 웹은 P4 체계를 씁니다. 제품군 축은 P4에 축을 더하는 별도 작업으로 남깁니다.

**분류 체계 v1 (위자드 선택 기록, 적용 보류)**

- **기술 분야 23:** 온디바이스 AI·모델(ai), 디스플레이(display), 통신·네트워크(network), 칩셋·부품(chipset), 카메라·센서(camera), 배터리·전력(power), 로보틱스(robotics), XR·공간 컴퓨팅(xr), 헬스·바이오센싱(health), 보안·프라이버시(security), OS·플랫폼(platform), 클라우드·엣지(cloud), 모빌리티·SDV(mobility), 소재·지속가능성(materials), 정책·규제·표준(policy), 오디오·음향(audio), 스마트홈 연결(smarthome), 생성형 AI 서비스(genai_service), 개발 도구·SDK(devtools), 결제·디지털 지갑(commerce), 에너지 관리(energy), 스마트 제조(manufacturing), 양자 기술(quantum)
- **제품군 18:** 스마트폰(phone), 폴더블(foldable), 태블릿·PC(tablet_pc), 웨어러블(wearable), TV·모니터(tv_monitor), 생활가전(appliance), 홈로봇·IoT(home_robot_iot), XR 기기(xr_device), 네트워크 장비(network_equipment), 전장(automotive), 의료기기(medical_device), 이어버드·오디오(earbuds_audio), 스마트 스피커·허브(smart_speaker), 상업용 디스플레이(signage), 공조·HVAC(hvac), 가정용 에너지 기기(home_energy), PC 주변기기(pc_peripheral), 카메라·드론(camera_drone)
- **규칙:** 기사당 분야 최대 3개, 제품군 0~3개, 영향 1개(기회·위험·관찰). 사업부 축은 따로 두지 않음
- 겹치는 항목(ai↔genai_service, platform↔smarthome, power↔energy, wearable↔earbuds_audio, appliance↔hvac, tv_monitor↔signage)은 노드 설명에 경계를 적어 분류 프롬프트에 넣음
- 반도체 자산 투자 기사는 기존 규칙대로 제외, 스마트 제조도 설비 투자 기사는 제외

## 4. 시안 3종

| | A 브리핑형 | B 탐색 워크벤치형 | C 토픽 레이더형 |
|---|---|---|---|
| 첫 화면 | 헤드라인 + 인사이트 3 + 분야별 핵심 | 좌 패싯 / 중 피드 / 우 인사이트 패널 | 분야 × 제품군 히트맵 + 선택 칸 상세 + 키워드 수명주기 |
| 잘 맞는 사람 | 경영진, 아침 요약 독자 | 기술 리더, 특정 분야 추적 실무자 | 전략·기획, 주간·분기 리뷰 |
| 강점 | 가독성, 구현 쉬움, 기존 다이제스트 재사용 | 찾기 속도, 필터 URL 공유 | 기간 인사이트 표현, 공백 영역 발견 |
| 약점 | 탐색 약함, 밀도 낮음 | 첫 화면 빽빽함 | 분류·롤업 선행 필요, 학습 비용 |
| 모바일 | 단일 컬럼 + 분야 칩 스크롤 | 피드/인사이트 탭 + 필터 시트 + 하단 탭바 | KPI 2×2, 히트맵 가로 스크롤 |

**추천:** 홈(`/`)은 A, 탐색(`/explore`)은 B, 주·월·분기 리포트(`/brief/*`)는 C로 조합. 하나만 고른다면 B.

## 5. 기간별 인사이트 분석

### 5.1 주기별 질문과 구성

| 주기 | 발행 | 질문 | 구성 |
|---|---|---|---|
| 일간 | 매일 05:00 KST | 어제 무슨 일이 있었고 무엇이 갑자기 늘었나 | 헤드라인·인사이트(기존 다이제스트), 분야별 핵심, 급상승 키워드 Top 10, 반응 급등, 신규 키워드 후보 |
| 주간 | 월 06:00, ISO 주 | 이번 주 큰 흐름 다섯 가지와 경쟁 구도 | Top 5 테마(클러스터), 분야·제품 점유율 변화, 기업·제품 Share of Voice, 신규→지속 키워드, 주목할 논문·저장소, 다음 주 행사 |
| 월간 | 매월 1일 | 어떤 주제가 붙고 있고 어디서 먼저 시작됐나 | 분야×제품 히트맵 변화, 동시출현 네트워크, 모멘텀 상·하위, 지역 확산 경로, 출처 품질 리뷰 |
| 분기 | 분기 첫 주 | 연구→제품 이동 정도, 전략 반영 사항 | 기술 성숙도 이동, 관심 대비 실체 괴리, 1·3·5년 로드맵 시사점(P7), 지난 분기 신호 회고 |

### 5.2 지표 카탈로그

| 지표 | 계산 | 입력 | 지금 가능? |
|---|---|---|---|
| 점유율 (SoV) | 기간 내 분야·제품·기업 기사 수 ÷ 전체, 직전 기간 대비 %p | 항목 + 분류 | 분류 필요 |
| 급상승 키워드 | z = (이번 빈도 − 기준 평균) ÷ max(기준 표준편차, 1), 최소 5건·독립 출처 3곳 | 정규 키워드 | 정규화 필요 |
| 신규 등장 키워드 | 이번 기간 첫 등장 + 직전 4개 기간 부재 + 독립 출처 3곳 이상 | 정규 키워드 | 정규화 필요 |
| 키워드 수명주기 | 신규 → 급상승 → 지속(±10%) → 하락(3기간 연속 감소) | 키워드 롤업 | 롤업 필요 |
| 동시출현 | 같은 카드 키워드 쌍의 PMI, 새로 생긴 강한 쌍 | 카드 키워드 | 정규화 필요 |
| 반응 모멘텀 | 스타·점수·좋아요 증가량의 EWMA 기울기 | 지표 스냅샷 | 가능 |
| 교차 신호 체인 | 논문 → 저장소 → 커뮤니티 → 언론 연결과 단계별 소요일 | arXiv ID·DOI·저장소 URL | P4 필요 |
| 지역 확산 | 최초 등장 지역 → 다른 지역 도달 일수 | 정규 키워드 + 지역 | 정규화 필요 |
| 출처 다양성 | 사건당 독립 출처 수, 1차 공식 비율, 도메인 편중도 | 출처 메타 | 가능 |
| 기술 성숙도 이동 | 분야별 트랙 구성비 변화 (논문·OSS ↓, 뉴스·리뷰 ↑ = 상용화 진행) | 트랙 + 분류 | 분류 필요 |
| 영향 분포 | 분야별 기회·위험·관찰 비중 | 영향 분류 | 분류 필요 |

### 5.3 계산 규칙

- 기간 경계: KST, 주 = ISO 주(월요일 시작), 분기 = 달력 분기
- 집계 단위: P4 전에는 항목, P4 후에는 사건 클러스터 (중복 보도 부풀림 제거)
- 기준선: 일 = 직전 28일, 주 = 직전 8주, 월 = 직전 6개월, 분기 = 직전 4분기
- 출처 보정: 트랙별 소스 수 차이 때문에 트랙 내 비중으로 먼저 정규화한 뒤 합산

### 5.4 주의할 점

- **소스 편중:** 카탈로그 1,070개 중 독립 언론 232, 개발자 포럼 195. 원시 건수를 쓰면 두 범주가 추세를 지배
- **키워드 표기 불일치:** 카드 엔진 2종이라 같은 개념이 다르게 적힘. 별칭 사전 없이는 급상승이 쪼개짐
- **행사 시즌:** CES·MWC·IFA·개발자 컨퍼런스 주간은 전 분야 동시 상승 → 행사 캘린더로 "예정된 급등" 표시
- **초기 데이터 부족:** 분기 기준선은 4분기가 쌓여야 의미. 그 전에는 리포트에 기준선 부족 명시

### 5.5 데이터 흐름

1. **한국어 카드 (10분, 기존):** 카드 LLM 출력 스키마에 분야·제품군·영향 추가 — 추가 LLM 호출 없음
2. **정규화 (10분, 신규):** 키워드 별칭 매핑, 분류 규칙 보정, 기업·제품명 추출
3. **일 롤업 (매일 04:30, 신규):** 날짜 × 차원(분야·제품·키워드·기업·트랙·지역)별 건수·클러스터 수·출처 수
4. **기간 집계·점수 (04:35, 신규):** 일 롤업을 주·월·분기로 합산, z-score·수명주기·점유율
5. **기간 리포트 (05:00 / 월 06:00, 확장):** 다이제스트 파이프라인 일반화, 모든 문장에 근거 ID, 불변 버전
6. **웹:** 홈·탐색·토픽·리포트, 관리 영역에 생성 이력

### 5.6 추가 테이블 (초안)

| 테이블 | 주요 컬럼 | 역할 |
|---|---|---|
| `taxonomy_nodes` | axis(field·product·impact), key, label_ko, parent_key, revision | 분류 체계와 리비전 |
| `item_labels` | item_id, axis, node_key, confidence, method(rule·llm), taxonomy_rev | 기사별 분류 |
| `keywords`, `keyword_aliases` | canonical, first_seen_at / alias → keyword_id | 표기 통일, 신규 판정 |
| `item_keywords` | item_id, keyword_id | 카드 키워드 → 정규 키워드 |
| `entities`, `item_entities` | kind(company·product·standard), name / item_id, entity_id | 기업·제품 언급량 |
| `daily_rollups` | day, dimension, key, items, clusters, sources, metric_sum | 기간 집계 원천 |
| `period_scores` | period, period_start, dimension, key, count, prev_count, z, state, rank | 급상승·수명주기·점유율 |
| `period_reports` | period, period_start, version, content JSONB, item_ids, model, status | 주·월·분기 리포트 (불변 버전) |

## 6. 실행 계획 (분류 → 롤업 → 화면)

| 단계 | 크기 | 내용 |
|---|:---:|---|
| R1 디자인 토큰·기본 규칙 | S | `globals.css` 토큰 교체(트랙·영향 색, 잉크 단계), keep-all·text-wrap, 본문 대비 상향, 트랙 배지 색. 기존 콘솔에 즉시 반영 |
| R2 분류 체계 v1·키워드 정규화 | M | 분야·제품군·영향 정의, 카드 스키마에 분류 필드, 기존 카드 소급 분류, 별칭 사전 |
| R3 일 롤업·기간 지표 API | M | 04:30 롤업 잡, 주·월·분기 집계와 점수, `/api/insights/*` |
| R4 독자 웹 | L | 선택 시안으로 홈·탐색·분야·제품·키워드·상세, 반응형, 검색 |
| R5 주·월·분기 리포트 | M | 다이제스트 파이프라인 일반화, 리포트 화면·아카이브 |
| R6 콘솔 → 관리 영역 | S | `/console` → `/admin`, 새 토큰, 리포트 이력·미분류 비율 화면 |

각 단계는 착수 시점에 TDD 단위 상세 계획을 별도로 작성합니다.

## 7. 결정 현황

| 항목 | 결정 |
|---|---|
| 시안 선택 | 시안 B(탐색) + C(레이더) — 설계: [`2026-10-04-07-reader-web-r4.md`](2026-10-04-07-reader-web-r4.md) |
| 분류 체계 | P4 체계 사용(분야 15·테마 75·사업부 6). 위자드 선택(분야 23·제품군 18)은 기록만 남기고 보류 |
| 공개 범위 | 로그인 없이 공개 |
| 리포트 생성 모델 | 호스트 Claude CLI (P7의 D1 "외부 LLM 미사용"과 다르므로 P7 착수 시 결정 기록 갱신 필요) |
| 착수 순서 | R1·R2 병렬 |
