# 시스템 점검표 · DX 테마 확장안 반영 계획

> **입력:** '레이더 콘텐츠 재검토 및 분석' 세션 산출물 두 개.
> - [News Insight 시스템 점검표](https://claude.ai/artifact/MgpyjLrMwAxiSVaSXyEy4W): 22개 항목, 기준 커밋 `c5ed82a`, 데모 DB 7천 건
> - [DX 기술 테마 확장안](https://claude.ai/artifact/LTMR1FJDtE3xr1BESVsU2d): 신규 분야 1개, 테마 14개, 감시 목록 9개
>
> **기준:** main `863b836` (P9 #17, 기술 레이더 #18 병합 후) · 운영 DB 항목 80,020건 · 최근 90일 카드 42,696건 · 2026-10-04

## 0. 점검표 이후 바뀐 사실

점검표는 P9 병합 전 브랜치와 데모 DB를 기준으로 썼습니다. 반영 전에 현재 상태와 실데이터로 다시 확인했습니다.

| 항목 | 점검표 판단 | 현재 상태 |
|---|---|---|
| SEC-1 CSP·HSTS | 없음 | **해결** (P9). CSP·COOP를 적용했고, HSTS는 실제 도메인일 때만 보냄 |
| OPS-3 호스트 잡 하트비트 | 없음 | **해결** (P9). `cards_stalled`가 40분 넘으면 알림. 대체 실행기는 미해결 |
| OPS-1 관측성 | 로그·지표·알림 없음 | **일부 해결** (P9). 운영 알림 11종, 콘솔, 메일. 구조화 로그와 지표 노출은 미해결 |
| PERF-1 인덱스 | 없음 | **사실 확인**. `items.first_seen_at`과 `item_cards.themes`·`businesses` GIN 모두 없음 |
| PERF-2 레이더 실시간 집계 | 분기 2.45초 (7천 건) | **더 심각**. 실데이터에서 캐시 없는 레이더가 주 10.8초, 월 7.9초, 분기 6.4초, 응답 140KB. 배포 직후 첫 요청은 15초 |
| DATA-1 스냅샷 누적 | 가장 큰 테이블이 될 것 | 지금은 2.7만 행, 4.8MB. 급하지 않음 |
| 테스트 수 | API 420 · 웹 49 · E2E 11 | API 492 이상, 웹과 E2E는 #18을 반영해 늘어남 |

## 1. 진행 원칙

- **역할 분담:** 레이더 화면과 통계는 '레이더' 세션이 만든 영역입니다(`public/radar.py`, `components/reader/radar/`, `lib/radar*`). STAT-*, WEB-1, QA-1, PRD-1의 화면 쪽은 그 세션에 맡깁니다. 이 세션은 공용 기반(인덱스, 롤업, 로그, 속도 제한, 카드·분류 파이프라인, 테마·소스)을 맡습니다. PR마다 건드리는 파일 범위를 미리 적어 충돌을 막습니다.
- **분류 개정 순서:** 재분류 비용을 먼저 줄이고(CLS-2), 체계 밖 신호를 수집하고(CLS-1), 그다음 테마를 바꿉니다. 지금 `TAXONOMY_REVISION`만 올리면 카드 3만 장 이상이 요약까지 다시 생성됩니다.

## 2. 단계별 계획

### 단계 A — 이번 주: 성능·운영 기반 (P0)

| ID | 할 일 | 완료 기준 |
|---|---|---|
| A1 · PERF-1 | 마이그레이션 0016으로 인덱스 추가<br>· `items(first_seen_at)`, `items(source_id, first_seen_at)`<br>· `item_cards` `themes`·`businesses` GIN<br>· `item_metric_snapshots(captured_at)`<br>· `items(body_expires_at) WHERE body_expires_at IS NOT NULL` | 7일 피드와 테마 필터의 EXPLAIN이 Index/Bitmap Scan으로 바뀌고, 레이더 응답 시간을 재측정해 기록 |
| A2 · OPS-2 | 공개 경로 속도 제한. 기본 Caddy 이미지에는 rate limit 모듈이 없음<br>· `ops/caddy/Dockerfile`에서 xcaddy로 `caddy-ratelimit`을 넣어 빌드<br>· IP당 분당 120회, `/radar*`는 20회<br>· 내부망 호출은 제외 | 부하 도구로 초당 20회 보내면 429가 나오고, 05:00 발행 작업에 영향 없음 |
| A3 · OPS-1 나머지 | API·Celery·CLI 진입점에 JSON 구조화 로그 한 번 설정 (요청 ID, 소스 키, 단계)<br>운영 알림에 레이더 응답 시간과 LLM 지연·실패를 추가<br>Prometheus는 단일 서버 개인 운영이라 보류 | 카드 엔진을 일부러 멈추면 30분 안에 알림이 오고, 로그에서 원인 단계를 찾을 수 있음 |
| A4 · PERF-3 | 배포 직후 옛 캐시 응답 문제<br>· 웹에 내부 키로 보호한 `revalidateTag("reader")` 경로 추가<br>· `scripts/release.sh`가 배포 뒤 이 경로를 호출<br>· API 응답에 `X-Schema-Version` 추가 | 응답 모양이 바뀐 배포 직후 첫 요청부터 새 응답으로 렌더링 |
| A5 · 소소한 정리 | QA-2: `E2E_BROWSER_CHANNEL` 환경 변수<br>WEB-2: `app/icon.svg`<br>DATA-2: 본문 만료 작업을 UPDATE 한 문장으로 | 각각 테스트 1개 이상 |

### 단계 B — 2~4주: 분류 파이프라인과 테마 v2 (P1)

| ID | 할 일 | 완료 기준 |
|---|---|---|
| B1 · CLS-2 | **분류만 다시 돌리는 경로**<br>· 카드 텍스트(번역·요약·키워드)와 분류를 분리: `item_cards`에 `classification_revision` 추가<br>· `pending_condition`을 "텍스트 대기"와 "분류 대기"로 나눔<br>· 재분류 프롬프트는 짧게: 입력은 `title_ko`·요약·키워드, 출력은 분류만<br>· 최근 90일을 최신 순으로 먼저 처리하고, 새 기사 카드가 항상 우선 | 테마를 추가해도 카드 텍스트는 그대로이고, 재분류 비용(토큰)이 카드 생성의 1/5 이하 |
| B2 · CLS-1 | **체계 밖 주제 수집**<br>· 카드 출력에 `topic_candidates`(0~2개, 테마가 잘 맞지 않을 때만)<br>· 콘솔 "미분류 신호" 화면: 후보 묶음별 건수, 추이, 예시 기사 | 한 달 뒤 후보 상위 20개가 근거 기사와 함께 보임. 다음 테마 개정의 입력이 됨 |
| B3 · KW-1 | **키워드 키를 저장 시점에 계산**<br>· `item_cards.keyword_keys`(JSONB, GIN)<br>· 별칭 표를 `keyword_aliases` 테이블로 옮기고 콘솔에서 편집, 변경된 키만 재계산<br>· 확장안의 별칭 목록을 초기값으로 넣음(아래 §3-3)<br>· 레이더 쿼리는 '레이더' 세션과 함께 `keyword_keys`로 전환 | 콘솔에서 별칭을 추가하면 배포 없이 10분 안에 레이더에 반영 |
| B4 · 테마 v2 | 아래 §3 확정안 적용<br>· `taxonomy/catalog.py`, 테스트 고정값(분야 16, 분야당 4~7)<br>· 프롬프트 포함·제외 경계 문구<br>· 웹 `lib/taxonomy.ts` 동기화<br>· `TAXONOMY_REVISION` 상향 후 B1 경로로 재분류<br>· 레이더에 **개정 시점 표시**(하락 오판 방지)<br>· 규제 기한(CRA, DPP, AI 기본법, NIST IR 8547)은 원문 관보·기관 문서로 다시 확인 | 신규 테마별로 첫 2주 안에 카드 20건 이상, 기존 테마 하락 신호에 개정 시점 주석 |
| B5 · 소스 | 소스가 0~3개인 영역 보강 (모두 probe로 V0·V2·V3 확인 후 시드)<br>· AI 데이터센터: DatacenterDynamics, Data Center Knowledge<br>· 출처증명·AI 보안: C2PA, Content Authenticity Initiative, OWASP GenAI<br>· AI 코딩: GitHub Changelog, JetBrains AI<br>· SDV: Automotive World<br>· 의료기기: 식약처 보도자료, Healthcare IT News<br>· 제품 규제: EUR-Lex 관보, KATS 기술규제 | 각 영역 V3 이상 2개 이상 |
| B6 · PERF-2 | **일 롤업(R3)**<br>· 04:30 `daily_rollups`: 날짜 × 차원(분야·테마·키워드 키·트랙·지역·사업부) × 건수·출처 수·공식 수<br>· 레이더 집계를 롤업 조회로 교체하되 응답 모양은 유지 ('레이더' 세션과 공동)<br>· 끝난 기간은 `radarClosed`(24시간) 캐시 | 실데이터에서 분기 레이더 300ms 미만 |
| B7 · STAT-1 | 소스 구성 편중 보정<br>· 트랙 내 비중으로 계산한 "보정 점유율"<br>· 출처당 테마별 하루 3건 상한<br>· 활성 소스 수 변화 기록 | 소스 50개를 추가한 주에도 보정 점유율이 ±1%p 안 |

### 단계 C — 1~2개월: 품질 (P2)

| ID | 할 일 | 담당 |
|---|---|---|
| CLU-1 | 다국어 임베딩(LM Studio)으로 묶음 후보를 찾고 엔터티 겹침으로 확정. `stories eval`로 F1 비교 후 전환 | 이 세션 |
| SIG-1 | 교차 신호 식별자 추가: CVE, 3GPP TS/TR, 특허 공개번호, Hugging Face 모델 | 이 세션 (추출) + 레이더 (차트 필터) |
| STAT-2 · STAT-3 | 진행 중 기간 보정, 소량 표본 통계 통일 | 레이더 세션 |
| WEB-1 | 레이더 페이지 400KB 이하 (Suspense 스트리밍, 상세는 클라이언트 조회) | 레이더 세션 |
| PRD-1 | 신호 규칙을 API로 옮겨 매일 저장 → 다이제스트·전략 프롬프트의 근거로 사용, 테마 구독 알림 | 공동 (저장·프롬프트는 이 세션) |
| QA-1 | 데모 시드의 심은 패턴 검출을 CI 회귀 테스트로 | 레이더 세션 |
| DATA-1 | 스냅샷 다운샘플링(30일 후 하루 1개, 180일 후 주 1개) | 이 세션, 테이블이 100MB를 넘으면 |

## 3. 테마 v2 확정안 (실데이터 수요 반영)

확장안이 제시한 기준(B 항목은 90일 50건 미만이면 감시 목록으로)을 운영 DB에 적용했습니다. 건수는 카드 키워드를 패턴으로 찾은 **대략치**입니다. 짧은 약어(ota, cra, rpm)가 섞여 부풀었을 수 있고, 반대로 기존 테마에 흡수된 보도는 빠졌을 수 있습니다.

### 3-1. 추가 (12개)

| 테마 키 | 이름 | 등급 | 90일 수요 | DX |
|---|---|---|---:|---|
| `mobile_edge__smart_home_iot` | 스마트홈·Matter·홈 IoT | A | 760 | DA·VD·MX |
| `software_dev__ai_coding` | AI 네이티브 개발·코딩 에이전트 | A | 417 | 의존성 |
| `robotics_auto__sdv_cockpit` | SDV·디지털 콕핏 | A | 412 | Harman |
| `cloud_infra__ai_datacenter` | AI 데이터센터·전력·냉각 | A | 202 | 의존성·DA |
| `policy_ip_standards__product_compliance` | 제품 규제 준수(CRA·DPP·수리권) | A | 71 | 전 사업부 |
| `security_privacy__ai_security_provenance` | AI 보안·콘텐츠 출처증명 | A | 61 | MX·VD |
| `cloud_infra__sovereign_ai` | 소버린 AI·클라우드 | B→추가 | 62 | 의존성·Networks |
| `emerging_science__home_energy` | 가정 에너지·전기화 | B→추가 | 57 | DA |
| `health_medtech__digital_biomarker` | 디지털 바이오마커·비침습 센싱 | A | 68 | Health·MX |
| `health_medtech__ai_samd` | AI 의료기기·SaMD | A | 37 | Health·MX |
| `health_medtech__health_data_interop` | 의료데이터 표준·상호운용 | B (권고: 추가) | 35 | Health·DA |
| `health_medtech__remote_care` | 원격진료·원격 모니터링 | B (권고: 추가) | 26 | Health |

**신규 분야 `health_medtech`(헬스·메드테크):**
- 권고는 4개 테마입니다. 의료 소스가 17개 있고 Health는 DX 사업부인데, 담을 칸이 `wearable_health` 하나뿐입니다.
- B 두 개(의료데이터, 원격진료)는 50건에 못 미칩니다. 다만 분야 단위로 보면 건수가 충분하고, B2(체계 밖 후보)로 3개월 뒤 다시 판단할 수 있어 함께 넣는 쪽을 권합니다. **결정 필요 (§4).**

### 3-2. 감시 목록으로 (테마 대신 별칭과 승격 조건)

- **에이징테크·돌봄 (6건):** 신호가 너무 적습니다. 승격 조건은 분기 30건입니다.
- **PQC 전환 (19건):** 기존 '포스트양자암호' 별칭을 유지합니다. NIST 2030년 기한 관련 보도가 분기 30건을 넘으면 승격합니다.
- **확장안의 감시 목록 9개는 그대로 따릅니다:** 위성 D2D, AI 글래스, Wi-Fi 8, 앰비언트 IoT, 월드모델·피지컬 AI, CPO, 기밀 컴퓨팅, AI 컴패니언, 6G.

### 3-3. 별칭 초기값 (B3 테이블에 넣음)

```
ntn += directtodevice, directtocell, d2d
c2pa ← contentcredentials, 콘텐츠자격증명
딥페이크 ← deepfake, deepfakes
sdv ← softwaredefinedvehicle, 소프트웨어정의차량, 소프트웨어중심차량
matter ← 매터, matterprotocol
cpo ← copackagedoptics, 코패키지드옵틱스
액체냉각 ← liquidcooling, 수냉식냉각
samd ← softwareasamedicaldevice, 소프트웨어의료기기
cra ← cyberresilienceact, 사이버복원력법
dpp ← digitalproductpassport, 디지털제품여권
wifi8 ← 80211bn, 와이파이8
월드모델 ← worldmodel, worldmodels, worldfoundationmodel
피지컬ai ← physicalai
앰비언트iot ← ambientiot
기밀컴퓨팅 ← confidentialcomputing
```

### 3-4. 결과 체계

| | 현재 | v2 |
|---|---:|---:|
| 분야 | 15 | 16 |
| 테마 | 75 | 87 |
| 분야당 테마 | 5 (고정) | 4~7 |

테스트의 "분야당 5개" 고정 단언은 "4~7개"로 바꿉니다. 카드당 테마는 최대 2개로 유지합니다. 그래서 기존 테마 건수가 일부 줄어드는데, 레이더에 개정 시점을 표시해 하락으로 오인하지 않게 합니다.

## 4. 결정이 필요한 것

| 질문 | 권고 | 대안 |
|---|---|---|
| 헬스·메드테크 테마 수 | 4개 (원격진료·의료데이터 포함) | 2개(A만) / 5개(에이징 포함) |
| 분야당 테마 수 규칙 | 4~7개 허용 | 5개 고정 (기존 하위 테마 9개 교체) |
| 재분류 범위 | 최근 90일 우선, 이후 과거는 한도 여유 시 | 전체 즉시 |
| 속도 제한 방식 | Caddy 커스텀 빌드 (`caddy-ratelimit`) | 앱 단(Next proxy) 제한 |

## 5. 일정 요약

| 주 | 범위 | PR |
|---|---|---|
| 1주차 | A1~A5 | 2개 (인덱스+로그 / 속도 제한+캐시) |
| 2~3주차 | B1 · B2 · B3 | 2개 |
| 3~4주차 | B4 · B5 (테마 v2 + 소스) → 재분류 실행 | 1개 |
| 4~6주차 | B6 · B7 (롤업, 보정 점유율. 레이더 세션과 공동) | 1~2개 |
| 이후 | 단계 C | 항목별 |
