# Phase 4 — 정규화·중복 제거·이슈 묶음·교차 신호·분류 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use dev_sp_executing-plans to implement this plan task-by-task.

**Goal:** 매일 들어오는 수만 건의 항목을 (1) 같은 기사·같은 사건끼리 묶고, (2) 논문→GitHub→커뮤니티→미디어로 이어지는 교차 신호를 잇고, (3) 분야 15·테마 75·DX 사업부 6·영향·범위(DX/의존/제외/무관)로 분류해, 콘솔과 다이제스트가 중복 없이 관련 있는 이슈만 보이게 합니다.

**Architecture:**
- **분류는 카드 생성과 한 번의 LLM 호출로 합니다.** 카드 스키마에 분야·테마·사업부·영향·범위·관련도(0~100)를 추가하고, 분류 체계 리비전이 바뀐 카드는 다시 만듭니다. 엔진은 D18 그대로입니다(Antigravity → Qwen).
- **중복·사건 묶음은 결정적(LLM 없이) 알고리즘입니다.** 한국어 카드 제목(언어 간 공통 표현)과 원제의 문자 3-gram으로 MinHash 64개 서명을 만들고, LSH 16밴드×4행을 DB 인덱스에 저장합니다. 새 항목만 후보를 조회해 유사도를 계산하는 증분 방식입니다.
- **교차 신호는 식별자 일치로 잇습니다.** arXiv ID, DOI, GitHub 저장소 URL을 항목 본문·URL에서 추출하고, 트랙이 다른 항목끼리 같은 식별자를 공유하면 연결합니다. 같은 이슈 묶음에 여러 트랙이 섞인 경우도 신호로 봅니다.
- **평가:** 관련성은 사용자 검토 라벨(P3.7)과 LLM 판정을 비교해 정확도를 표시합니다. 중복 임계값은 표본 쌍을 Antigravity가 "같은 사건인가"로 판정한 은표준(silver label)으로 P/R/F1을 계산해 정합니다.

## Global Constraints
- 분류 체계: v3에서 쓰던 분야 15 × 테마 5 = 테마 75 (요구사항 §9), DX 사업부 6: MX(모바일·온디바이스 AI)·VD(디스플레이·영상)·DA(생활가전·홈로봇)·NETWORKS(5G Adv·6G)·HEALTH(디지털 헬스·의료기기)·HARMAN(전장·SDV), 영향: opportunity·risk·watch
- 범위(scope): `dx`(DX 제품·기술) · `dx_dependency`(완제품 성능·원가에 직결되는 부품·기술 의존성) · `excluded`(메모리·파운드리 증설 같은 반도체 자산 투자 자체, §1) · `irrelevant`
- 분류 체계 리비전 `TAXONOMY_REVISION`이 바뀌면 카드를 다시 만듦(새 항목 우선)
- 근접 중복 임계값·사건 임계값은 설정값(기본 0.6 / 0.35), 평가 명령으로 조정
- 이슈 묶음은 72시간 창에서만 이어 붙임(같은 주제의 다른 날 사건은 새 묶음)
- 모든 처리는 증분·멱등. 10분 주기(Celery `stories.cluster`)

## Tasks
1. 분류 체계 모듈(`taxonomy/catalog.py`) + 테스트(15/75/6/3, 키 고유)
2. 카드 스키마 확장(분류 필드·검증·프롬프트에 분류 체계 요약) + `item_cards` 분류 컬럼(마이그레이션 0010) + 리비전 불일치 재생성
3. 중복 키 정규화(`dedup_url`: AMP·모바일 호스트·트래킹 제거) + MinHash/LSH 서명(`stories/minhash.py`)
4. `item_signatures`·`item_lsh`·`stories`·`story_items` 테이블(마이그레이션 0011) + 증분 묶음 서비스(정확 중복 → 근접 중복 → 사건) + Celery 잡 + CLI `stories run`
5. 교차 신호: 식별자 추출(`signals/refs.py`), `item_refs` 테이블, 체인 조회(트랙 순서·날짜) + Celery 잡
6. 평가: `stories eval`(은표준 쌍 판정, 임계값별 P/R/F1), 관련성 일치율(검토 라벨 vs LLM)
7. 콘솔 API: 카드 피드에 분류·묶음 정보와 필터(분야·사업부·영향·범위, 무관·제외 숨김), `/stories`, `/signals`, 검토 통계에 분류기 일치율
8. 웹: 카드 뉴스(분류 배지·"관련 기사 N건"·필터), 이슈 묶음 화면, 교차 신호 화면, 관련성 검토에 LLM 판정 표시
9. 다이제스트 입력 개선: 무관·제외 제거, 묶음 대표 항목만, 사업부별 구성
10. 문서·검증·PR
