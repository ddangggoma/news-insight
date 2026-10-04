# 실행 추적 — 점검표·테마 v2 계획 (08 + 09)

> 재개할 때 이 파일부터 읽습니다. `[ ]`는 남은 일, `[x]`는 끝난 일(PR 번호 포함)입니다.
> 계획 원문: [08](2026-10-04-08-inspection-and-taxonomy-v2.md) (점검표·실행 순서), [09](2026-10-04-09-taxonomy-v2-tech-sensing.md) (테마 v2: 사업 태그 삭제, 12분야·62테마, 신호 유형, 기술 레지스트리)
> 규칙: 단계마다 브랜치 → `scripts/dev.sh verify` + `scripts/dev.sh web-e2e` → 푸시 전 비밀값 검사 → PR → CI 통과 → 병합 → **운영 트리에서 배포**: `cd /Users/ggoma/WorkSpace/NEWS_INSIGHT-live && git fetch -q origin && git checkout -q --detach origin/main && docker compose up -d --build`. launchd 작업은 운영 트리에서 돌므로 개발 트리 브랜치는 자유. 개발 중 운영 DB에 `alembic upgrade`를 직접 실행하지 말 것.

## 단계 A — 성능·운영 기반 (PR #20, 배포 완료)
- [x] A1 인덱스 마이그레이션 0016 (items.first_seen_at, (source_id, first_seen_at), item_cards themes GIN, metric_snapshots.captured_at, items.body_expires_at 부분 인덱스) + EXPLAIN·레이더 재측정
- [x] A2 Caddy 커스텀 빌드(caddy-ratelimit): IP당 분당 120회, /radar* 20회
- [x] A3 JSON 구조화 로그(API·Celery·CLI) + 레이더 응답 시간·LLM 지연 알림
- [x] A4 배포 직후 캐시 갱신: 웹 내부 revalidate 경로 + release.sh 호출 + X-Schema-Version
- [x] A5 E2E_BROWSER_CHANNEL, app/icon.svg, 본문 만료 UPDATE 일괄

## 단계 B — 분류 파이프라인과 테마 v2
- [x] B1 분류 전용 재분류 경로 (PR #21, 배포) (classification_revision, 분류 전용 프롬프트, 별도 레인)
- [x] B2 topic_candidates (PR #21, 배포) + 콘솔 "미분류 신호"
- [x] B3' 기술 레지스트리 (PR #22, 배포·시드 완료) (technologies·aliases 테이블, item_cards.technology_keys GIN, 콘솔 편집·후보 대기열, 시드 약 350)
- [x] B4' 체계 v2 (PR #23, 배포 + 잠정 매핑 52,509장): catalog 12분야·62테마·SIGNAL_TYPES, signal_type 컬럼, 사업 태그 전면 삭제(API·웹·레이더·브리핑·다이제스트·전략 분야별 섹션), 테스트, 웹 taxonomy.ts, 레이더 개정 시점 표시
- [ ] B4'-run 전체 즉시 재분류 실행·검증 (기술 테마 없는 관련 카드 < 5%, 표본 200건 정확도 85%)
- [x] B5 소스 보강 (PR #24, 8곳 시드 완료)
- [x] B6 레이더 응답 캐시(Redis, 끝난 기간 24h·진행 중 15m) + 10분 예열 (PR #25) — 임의 필터 조합 때문에 롤업 대신 해석된 보기 단위 캐시로 구현
- [x] B7 보정 점유율 (PR #25: normalized_share, 출처·일 3건 상한 capped, 활성 소스 수는 KPI sources)

## 단계 C — 품질
- [ ] C1 CLU-1 다국어 임베딩 묶음 (LM Studio) + stories eval 비교 — 평가 완료·보류: nomic-embed-text-v1.5는 한국어 제목에 무효(고유사도·MinHash 미검출 쌍 중 같은 사건 4%). 다국어 모델(bge-m3 등) 내려받기 승인 필요
- [x] C2 SIG-1 식별자 확장 (CVE, 3GPP, 특허, Hugging Face) (PR #26, 배포 후 refs-backfill 30일)
- [x] C3 STAT-2 진행 중 기간 보정 (PR #28: 같은 시점 비교 `paced`, 월요일 하락 25→0/26) / STAT-3 소량 표본 통계 통일 (PR #29: 신호 규칙을 API `public/signals.py`로, 공통 `public/stats.py` — 포아송·von Neumann z, 두 비율 z, 이항 0건 확률, 수축 순위. 심은 패턴 20/20, 국내 공백 후보 12→2)
- [ ] C4 WEB-1 레이더 페이지 경량화 (≤400KB)
- [x] C5 PRD-1 신호 저장 → 다이제스트·전략 근거 (PR #30: `radar_signals` 테이블·04:40 저장, 다이제스트·페르소나·작성자 입력, 브리핑 "레이더 신호" 패널. 테마 구독 알림은 채널 결정 필요로 보류)
- [x] C6 QA-1 데모 시드 패턴 회귀 테스트 (PR #27: `dev.sh radar-qa`, CI 단계, 규칙별 후보 노출. 시드 보강 — 메타버스 재등장이 토요일에 걸려 약했고 OLED 이동은 표본이 문턱 미달)
- [ ] C7 DATA-1 스냅샷 다운샘플링

## 기록
- B4': 12분야·62테마·신호 유형 10, 사업 태그 전면 제거(API·웹·레이더·브리핑·다이제스트·전략 분야별), 잠정 매핑(`taxonomy provisional`, 리비전 .0)으로 독자 화면 공백 없이 전환, 새 기사 없으면 전 레인 재분류, 레이더 개정 안내. 배포 후 `taxonomy provisional` 실행 필요
- B3': 레지스트리 274개(YAML 시드), DB 트리거로 technology_keys 계산, 레이더·인사이트가 정규식 대신 저장 키 사용, 콘솔 편집·후보 대기열, 03:45 키·이름 갱신. 배포 후 `technologies seed` 필요
- B1·B2: 분류 전용 레인(Antigravity 1레인, Qwen은 새 기사 뒤), 재분류 3회 실패 시 포기, topic_candidates + 콘솔 미분류 신호. 운영 트리(NEWS_INSIGHT-live) 도입, verify가 운영 DB를 마이그레이션하지 않도록 수정
- 단계 A 측정: 시간 창 1,018→31ms, 테마 필터 379→2ms. 레이더는 6~10초 그대로. 원인은 키워드 축 `_series`(정규식+별칭 JSON, 8개 기간 집계) → B3'(technology_keys)와 B6(롤업)에서 해결
- 2026-10-04: 계획 확정. 재개 예약(세션 크론, 매시 17분) 등록.
