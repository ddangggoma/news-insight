# 사건 확장 분석 — 한 사건을 시계열(주체의 궤적)과 공간(대상의 지형)으로 펼치기

> 요청(2026-10-13): "동향 보고서 작성 시 어떤 Event를 보고 시계열과 공간 계열로 확장하는 분석이 필요하다. 예를 들어 '얀 르쿤이 META를 퇴사해서 JEPA 기술 스타트업을 차린다'는 A가 B를 하는 것인데, A의 과거와 미래 행적을 모두 찾아보고 B에 대해 A 외 다른 주체들의 행위를 찾아보면 인사이트를 끌어내기 쉽다. 이 논리를 적용할 방안을 여러 측면으로 검토·설계하라. 관련 논문·연구를 모두 조사해 설계에 반영하라." 추가 요청: "동향 보고서 작성 측면의 연구 내용도 모두 조사해 포함하라."
> 추가 요청(2026-10-13): "인물뿐 아니라 내가 주는 주제에 대해서 동향 보고서를 작성하도록 수정", "웹포털에서 주제나 정보를 주면 서버에서 Claude CLI Opus로 동향 보고서를 HTML로 작성", "콘솔이 아니라 유저 페이지에서 요청 및 열람".
> 상태: **R1 주제 요청 보고서 구현(§12)**, X1~X8은 설계. 문서 번호는 14가 계정 계획(2026-10-06)과 겹쳐 17로 옮겼다. 실행 규칙은 [10-execution-progress](2026-10-04-10-execution-progress.md)와 같다(브랜치 → verify → PR → CI → 병합 → `NEWS_INSIGHT-live/scripts/deploy.sh`).

---

## 0. 한 장 요약

- **핵심 아이디어: 사건 = 역할이 있는 칸(slot)의 묶음.** "르쿤(주체)이 Meta(출발지)를 떠나 AMI Labs(결과 조직)를 세워 JEPA·월드 모델(대상 기술)을 한다." 칸 하나만 비우고 나머지를 고정해 검색하면 확장 방향이 정해진다.
  - 주체 고정 + 시간 이동 → **시계열 축(T)**: 주체의 과거 궤적과 예고된 미래 행보
  - 대상 고정 + 주체 이동 → **공간 축(S)**: 같은 대상(B)을 두고 다른 주체들이 한 일 = 경쟁 지형
  - 행위 유형 고정 + 주체·대상 이동 → **유사 사례 축(P)**: "빅테크 핵심 연구자 → 창업" 같은 사건의 선례와 그 결과(기저율)
  - 출발지·상대방 고정 → **상대방 축(C)**: Meta는 그 뒤 무엇을 했나
  - 지역·시장 이동 → **지리 축(G)**: 어느 나라·시장에서 먼저, 국내 공백
  이 구조는 시간 지식그래프(TKG) 예측 연구의 질의 형태 `(s, r, ?, t)` · `(?, r, o, t)`와 같다(§2-B).
- **현재 시스템에 없는 것 세 가지:** ① 인물 축(카드 프롬프트가 인물을 일부러 뺀다), ② 이슈(story) 위의 **구조화된 사건 레코드**(누가·무엇을·누구에게·언제·어떤 양태로), ③ **수집 이전의 역사**(코퍼스가 2026-10-03부터라 10일치뿐).
- **실측(2026-10-13 운영 DB):** 르쿤 관련 기사 82건이 **16개 이슈로 흩어져** 있다. 10/12 한국 방문 발언 하나가 6개 이슈, 10/03~05 "AI 멸종론 일축" 발언이 4개 이슈다. 월드 모델·JEPA 기사 172건 중 154건은 기업 태그가 없고, AMI Labs·World Labs·Thinking Machines는 레지스트리에 없다. **이슈 묶음만으로는 "주체의 궤적"을 만들 수 없다.** 사건 레이어가 필요하다.
- **설계 결론:** PostgreSQL 안에 `events`(역할 인자·양태·시점 정밀도·이중 시간) + `entity_states`(소속·직책 같은 시간 유효 사실) + `expectations`(예고·관찰 지표)를 둔다. 하루 약 600~1,500개 사건을 로컬 Qwen으로 추출하고, 부족한 과거는 Wikidata·OpenAlex·GitHub·HN에서 **필요할 때만** 채운다. 확장 질의 5종(T·S·P·C·G)의 결과를 **사건 문서(dossier)**로 묶어 Claude 브리핑 단계에 넘긴다. 보고서는 정보분석 작법(BLUF, 핵심 가정 점검, 경쟁 가설, 관찰 지표, ICD 203 확률·확신도 표현)을 따른다.
- **단계:** X1 인물 레지스트리 → X2 사건 추출 → X3 이력 백필·상태 → X4 확장 API → X5 사건 문서·브리핑 → X6 관찰 지표 성적표 → X7 웹 → X8 평가. 8개 PR.

### 0-1. 입력은 주제다 — 주제 → 핵심 사건·주체 → 확장

처음 설계는 "사건 하나(A가 B를 한다)"에서 출발했다. 실제 요청은 더 넓다. 독자는 **주제**를 준다("월드 모델", "온디바이스 AI 칩 경쟁", "얀 르쿤의 AMI Labs 창업"). 그래서 입력을 세 형태로 일반화하고 모두 같은 흐름으로 처리한다.

| 입력 | 예 | 처리 |
|---|---|---|
| 주제 | "월드 모델", "온디바이스 AI 칩 경쟁" | 검색 계획 → 근거 → 근거에서 **핵심 사건과 주체를 뽑고** 각각 확장 |
| 개체(인물·기업) | "얀 르쿤", "Figure AI" | 개체 이름이 검색 계획의 people/companies로 들어간 주제. T축(그 개체의 궤적)이 중심 |
| 사건 | "르쿤이 Meta를 떠나 JEPA 스타트업 창업" | 사건 문장이 주제, 설명란이 정보. 주체(T)와 대상(S)을 모두 확장 |

흐름(§12에서 구현):

1. **검색 계획** — Claude가 주제를 한국어·영어 표기, 기업, 인물, 의미 검색 문장, 제외 단어, 축별 질문(시계열·지형·선례·DX)으로 바꾼다(STORM의 관점별 질문).
2. **근거 수집** — 키워드·등록 기업·의미 검색(카드 임베딩)·주제 파일 조건으로 카드를 모으고, 이슈당 1건, 주별 균형을 맞춰 최대 110건. 전체 일치분에 대해 주별 추이, 기업별 첫 등장·최근 건수, 소식 유형 구성 변화, 지역·트랙, 투자·제휴 거래, 주체별 타임라인을 계산한다.
3. **작성** — Claude가 근거만으로 핵심 사건(양태 포함)을 뽑고 T·S·P·G축과 DX 시사점, 가정·경쟁 가설·관찰 지표를 쓴다. 수집 이전 역사와 선례는 배경지식으로 쓸 수 있되 "배경지식·검증 필요"로 표시한다.
4. **검증·렌더링** — 받지 않은 카드 인용은 지우고, 인용 없는 '근거' 주장은 배경지식으로 내린다. 스크립트 없는 단일 HTML과 Markdown·Word·PowerPoint로 낸다.

X1~X8(사건 레이어·인물 레지스트리·이력 백필)이 들어오면 2단계의 근거에 **구조화된 사건과 수집 이전 이력**이 더해지고, 3단계에서 LLM이 사건을 다시 뽑는 일이 줄어든다. R1은 지금 데이터로 바로 쓰는 버전이다.

---

## 1. 문제 정의

### 1-1. 사건의 표현

동향 보고서의 사건 문장 "A가 B를 한다"를 다음 레코드로 본다.

```
Event = ⟨ type(행위 유형), mode(양태), args{역할 → 개체}, time(시점·정밀도), place, evidence(근거 기사), confidence ⟩

예) type=found, mode=asserted,
    args = { agent: person:yann-lecun, origin: company:meta, result_org: company:ami-labs,
             tech: tech:jepa, tech: tech:world-model, location: region:eu(파리) },
    time = 2025-11 (precision=month)
```

`A`와 `B`는 한 개가 아니다. 위 사건에는 **주체(르쿤)·출발지(Meta)·결과 조직(AMI)·대상 기술(JEPA)** 네 칸이 있고 칸마다 확장할 수 있다. 사용자가 말한 "A의 과거·미래"와 "B에 대한 다른 주체의 행위"는 이 중 두 칸(주체, 대상 기술)의 확장이다.

### 1-2. 다섯 확장 축

| 축 | 고정 | 이동 | 질문 | 르쿤 사례에서 나오는 것 |
|---|---|---|---|---|
| **T 시계열** | 주체 A | 시간 | A는 원래 무엇을 해 왔고 다음에 무엇을 할까 | LeNet(1989) → FAIR 설립(2013) → 튜링상(2018) → JEPA 입장 논문(2022) → I-JEPA·V-JEPA(Meta) → 퇴사·창업 → 대형 시드 → H-JEPA 공개·방한 발언(2026-10). **"전환"이 아니라 10년 주장의 상업화 = 확신 단계 상승** |
| **S 공간** | 대상 B | 주체 | 같은 기술을 누가, 어떤 단계로 하고 있나 | World Labs(페이페이 리), Google DeepMind Genie, NVIDIA Cosmos, Meta V-JEPA 계열(출발지가 같은 기술을 계속), 국내 연구기관·기업. 진입 순서·자본 규모·방식(연구형 vs 제품형) |
| **P 유사 사례** | 행위 유형 | 주체·대상 | 비슷한 일이 전에 있었나, 어떻게 끝났나 | 빅랩 핵심 인물의 창업: SSI(서츠케버), Thinking Machines Lab(무라티), World Labs, Inflection → Microsoft, Character.AI → Google, Adept → Amazon. **"2년 안에 라이선스·인재 인수형 거래로 흡수된 비율"** 같은 기저율 |
| **C 상대방** | 출발지·상대 | 시간 | 떠난 쪽·맞은편은 어떻게 반응했나 | Meta의 초지능 조직 재편, 연구 조직 변화, 같은 기술(V-JEPA) 지속 여부 |
| **G 지리** | 사건 | 지역·시장 | 어디서 먼저, 어디가 비었나 | 파리·뉴욕·몬트리올·싱가포르 거점, 한국 방문 발언(제조 데이터), 국내 보도 시차 |

> 사례의 코퍼스 밖 사실(경력·투자자·경쟁사)은 웹 확인 결과와 일반 지식이며, 구현 후에는 §5-4 백필 소스의 근거 링크로 대체한다. 시드 투자(2026-03, 약 10.3억 달러, 투자자에 NVIDIA·삼성·Toyota Ventures 등 포함)는 공개 보도로 확인했다([SiliconANGLE](https://siliconangle.com/2026/03/10/yann-lecuns-new-startup-ami-labs-raises-1-03b-train-world-models/), [Sifted](https://sifted.eu/articles/yann-lecun-ami-labs-meta-funding-round-nvidia)). **삼성이 투자자**라서 이 사건은 삼성 DX 관점에서 `relation=self` 연결을 가진다. 확장 분석이 없으면 놓치는 고리다.

### 1-3. 확장 결과에서 인사이트를 만드는 연산

확장한 집합을 늘어놓는 것만으로는 인사이트가 아니다. 집합 위에서 다음 판정을 계산하고 문장으로 만든다.

| 연산 | 입력 | 판정 | 보고서 문장 예 |
|---|---|---|---|
| **궤적 정합성** | T축 사건 목록, 이전 입장 | 연속 / 격상 / 전환 / 역전 (브리핑 B1의 continuity와 같은 어휘) | "르쿤의 창업은 2022년 JEPA 주장의 연속이며, 연구 논문 → 10억 달러 회사로 **격상**" |
| **약속 수준(commitment)** | 사건 유형의 사다리: 발언 < 논문 < 오픈소스 < 제품 예고 < 투자 유치 < 출시 < 인수 | 사다리 위치의 변화 | "말 → 돈: 실행 단계로 넘어감" |
| **혼잡도·진입 단계** | S축 주체 수, 진입 시점, 자본 | 개척 / 초기 진입 / 혼잡 / 정리(Rogers 확산 단계 근사) | "월드 모델: 10억 달러급 독립 진입자 2곳 + 빅테크 3곳 = 초기 경쟁 단계" |
| **기저율(outside view)** | P축 선례와 결과 | 결과 분포 | "유사 선례 6건 중 3건이 2년 내 빅테크 라이선스·인재 인수로 끝남" |
| **상대방 효과** | C축 사건 | 공백 / 대체 / 경쟁 강화 | "Meta는 같은 기술 라인(V-JEPA)을 유지 → 직접 경쟁 구도" |
| **입장 지도** | 발언 사건의 stance | 대상 주제별 찬반 | "AI 위험론: 르쿤(낙관·공학 문제) vs 아모데이(경고)" |
| **선행 지표** | T·S축 사건의 시차 | 사람 이동 → 논문 → 오픈소스 → 제품 | "핵심 인재 이동은 기술 상업화의 선행 신호"(Zucker·Darby, §2-E) |
| **관찰 지표(signpost)** | 예고·계획 사건, 선례의 다음 단계 | 기한 있는 기대 | "다음 6개월: AMI 첫 공개 모델, 제조·로봇 파트너 발표, Meta 대응" |
| **DX 연결** | 개체의 relation(self/competitor/supplier/partner) | 기회 / 위험 / 관찰 | "삼성 투자 연결 → 피지컬 AI 협력 기회, 방한 발언의 '제조 데이터' 강조와 일치" |

---

## 2. 관련 연구 조사와 적용

조사 범위는 일곱 갈래다. 각 갈래에서 **무엇을 가져오고 무엇을 가져오지 않는지**를 적었다. 출처는 §11.

### A. 사건 추출과 표현

| 연구 | 핵심 | 적용 |
|---|---|---|
| **5W1H 추출 — Giveme5W1H** (Hamborg 외, INRA 2019) | 기사의 주 사건을 누가·무엇을·언제·어디서·왜·어떻게로 추출. 전문가 평가 정밀도 0.73, 앞의 네 W만 0.82 | 사건 레코드의 최소 칸 = 4W(who·what·when·where). why·how는 요약문으로만 두고 구조화하지 않는다(정밀도가 낮음) |
| **CAMEO → PLOVER/POLECAT** (Open Event Data Alliance; Halterman 외 2023) | 행위자-행위-대상 코딩. PLOVER는 CAMEO 20개 상위 범주·204개 하위를 16개로 줄이고 **양태(mode)** 필드를 추가: 과거·미래·가정·부정 | ① 행위 유형은 **작고 닫힌 목록**(§4-2, 24종). ② **양태를 별도 칸**으로 둔다. "~할 계획", "~설", "부인"이 사실로 둔갑하지 않게 하고, 미래 행적(T축의 앞쪽)을 이 칸으로 잡는다 |
| **Neon** (Singhania 외, 2024, MPI·Microsoft) | 뉴스에서 개체 간 상호작용을 OpenIE 튜플로 뽑아 **개체 중심·타임스탬프 그래프** 구성 → 시간·개체 질의 QA 향상 | 우리 설계와 같은 방향. 다만 자유 술어(OpenIE) 대신 닫힌 유형을 쓴다. 자유 술어는 집계·기저율 계산이 안 된다 |
| **MAVEN-ERE** (Wang 외, EMNLP 2022) | 사건 간 관계 4종: 공참조·시간·인과·하위 사건. 관계를 함께 학습하면 성능 향상 | `event_links`의 관계 어휘를 여기서 가져온다. 단 **인과는 자동 생성하지 않는다**(정확도 낮음, 아틀라스의 "선후 ≠ 인과" 원칙 유지). 자동 링크는 공참조·선후·하위 사건·같은 패턴만 |
| **교차 문서 사건 공참조 — SECURE** (Min 외, ACL 2024), X-AMR (Ahmed 외, 2024) | LLM이 사건을 요약하고 작은 모델이 표현을 정제. 쌍 비교는 제곱 비용이라 LLM에 그대로 쓰면 비싸다 | 우리는 이미 MinHash·임베딩·LLM 판정으로 **기사 → 이슈** 공참조를 한다. 사건 레이어에서는 **같은 (유형, 주체, 대상) ± 7일** 후보만 판정해 제곱 비용을 피한다(§5-3) |
| **스키마 유도** (Dror·Wang·Roth, EACL 2023 Findings) | LLM으로 복합 사건의 하위 사건·인자·관계 스키마를 수작업 없이 생성 | "창업" 같은 유형의 **전형적 다음 단계**(시드 → 첫 모델 → 파트너십 → 시리즈 A / 인수)를 스키마로 만들어 관찰 지표 후보로 쓴다(§5-6) |
| **LLM 사건 추출의 한계** (2025 서베이·입장 논문) | 약한 제약에서 환각, 문서 간 시간·인과 연결 취약, 긴 맥락의 지식 관리 한계. 사건 스키마·사건 저장소를 LLM의 비계로 쓰자고 제안 | JSON 스키마 강제, 인자는 **레지스트리 키 또는 원문 표기**만 허용, 시간은 규칙으로 정규화. 장기 기억은 LLM이 아니라 DB(`events`)가 맡는다 |

### B. 시간 지식그래프와 예측

| 연구 | 핵심 | 적용 |
|---|---|---|
| **EventKG** (Gottschalk·Demidova, ESWC 2018; SWJ 판) | Wikidata·DBpedia·YAGO·Wikipedia 사건 목록에서 69만 사건·230만 시간 관계. SEM 모델. 저널판은 **인물 전기 타임라인 생성** | 사건 모델(SEM: 사건·행위자·장소·시간)과 **인물 전기 타임라인**을 그대로 T축 목표로 삼는다. 과거 이력의 1차 공개 출처로 Wikidata를 쓴다(§5-4) |
| **Zep / Graphiti** (Rasmussen 외, 2025) | 이중 시간: 사건 발생 시각과 수집 시각. 엣지마다 유효 구간(t_valid, t_invalid). 모순되는 새 사실은 **삭제가 아닌 무효화**. 상대 시간 표현("2주 전")을 기준 시각으로 절대화 | `entity_states`를 이중 시간으로 설계(§4-4): 르쿤 소속 Meta(2013-12 → 2025-11)는 지우지 않고 닫는다. "그때 우리가 알던 것"을 재현할 수 있어 브리핑 회고·성적표가 가능해진다 |
| **TKG 예측: RE-NET, TLogic** (Liu 외, AAAI 2022) | TLogic은 시간 순서를 지키는 랜덤 워크로 **시간 논리 규칙**을 뽑아 설명 가능한 예측. 같은 어휘를 쓰는 다른 데이터에 규칙 이전 가능 | P축 기저율을 "규칙"으로 표현: `found(x, org) ∧ depart(x, bigtech) → within 24m: license_deal(org, bigtech′)`. 규칙의 지지도·신뢰도를 그대로 보고서에 쓴다(설명 가능) |
| **LLM 인컨텍스트 TKG 예측** (Lee 외, EMNLP 2023) | 과거 사실을 프롬프트로만 넣어도 지도학습 SOTA와 비슷(Hits@1 −3.6%~+1.5%). 개체 이름을 숫자로 바꿔도 거의 같음 → **빈도·최근성 패턴**을 활용 | ① 미래 행보 추정에 별도 모델을 학습하지 않는다. 구조화된 과거 사건을 LLM에 넣는 것으로 충분. ② **빈도·최근성 기준선**을 반드시 함께 계산해 LLM 판단과 비교(같은 말을 하면 근거가 약한 것) |
| **시간 인식 GraphRAG** — TG-RAG, DyG-RAG, STAR-RAG, T-GRAG (2025) | 같은 사실도 시점이 다르면 다르다. 시간 노드 계층·**동적 사건 단위**(DyG-RAG: 의미 + 시간 고정점, 개체를 공유하고 시간이 가까운 사건끼리 연결)·시간 정렬 검색으로 토큰 절감·정확도 향상 | 사건 문서(dossier)를 만들 때 **시간 창을 먼저 자르고** 그 안에서만 검색. "개체 공유 + 시간 근접" 링크는 DyG-RAG와 같은 규칙으로 만든다. 그래프 DB는 쓰지 않는다(단일 서버, PostgreSQL 재귀 CTE로 2-hop이면 충분) |

### C. 타임라인과 이야기 구조

| 연구 | 핵심 | 적용 |
|---|---|---|
| **TDT** (Allan 외, 1998~2002) | 주제 탐지·추적: 새 사건 탐지, 사건 묶기 | 이미 이슈 묶음이 이 역할 |
| **SemEval-2015 Task 4 TimeLine** (Minard 외) | 대상 개체(인물·조직·제품)별로 여러 문서의 사건을 찾아 시간순 정렬. NewsReader 프로젝트에서 나옴. 최고 F1 **7.85**(원문에서 끝까지), 실패 원인은 파이프라인 오류 전파 | 사용자가 말한 "A의 과거 행적"이 정확히 이 과제다. 완전 자동은 어렵다는 근거 → ① 원문 전체가 아닌 **이슈 대표 기사 + 카드 요약**에서 추출, ② 인물·기업은 **레지스트리 키로 고정**해 개체 공참조 오류를 없앤다, ③ 검토 큐로 정밀도를 표본 측정 |
| **사건 진화 그래프** (Yang·Shi·Wei, IEEE SMC-A 2009) | 내용 유사도·시간 근접·문서 분포 근접으로 사건 간 진화 관계 그래프 | `event_links`의 `continues` 판정 점수에 같은 세 요소를 쓴다 |
| **Connecting the Dots / Metro Maps** (Shahaf·Guestrin·Horvitz·Leskovec, 2010~2015) | 이야기 갈래를 지하철 노선처럼: 역 = 기사 묶음, 노선 = 일관된 갈래. "Crimea" 예시는 러시아·우크라이나·서방 관점 3노선 | **S축 화면**을 노선도로: 노선 = 주체(르쿤/AMI, World Labs, DeepMind, Meta), 역 = 사건. 갈아타는 역 = 두 주체가 같이 나오는 사건(투자·제휴) |
| **Story Forest** (Liu 외, CIKM 2017 → TKDD 2020) | 사건을 묶고 사건을 이야기 나무로 온라인 확장. 생성한 사건 연결 83%가 논리적으로 맞음(복잡한 이야기 그래프 33%) | **단순한 구조가 더 맞다**는 근거. 사건 연결은 나무(부모 하나)로 두고 그래프 전체를 만들지 않는다 |
| **LLM-TLS** (Hu·Moon·Ng, ACL 2024) | LLM을 의사 정답자로 써서 **흐름 데이터에서 증분 사건 묶기** → 사건 타임라인과 주제 타임라인 모두 생성 | 사건 공참조 판정(§5-3)을 같은 방식(증분, LLM 판정)으로. 단 후속 연구가 측정한 토큰 사용량이 약 47M으로 큼 → 후보 축소가 필수 |
| **CHRONOS** (Wu 외, NAACL 2025 Findings) | 뉴스 주제를 받아 **스스로 질문을 반복 생성**하며 과거 기사를 검색해 타임라인 작성. 오픈 도메인에서 닫힌 도메인 SOTA에 근접. 사례 분석에서 제품 발표 하나 누락, 날짜 하나 오류 | 백필(§5-4)에서 "르쿤의 과거 주요 사건은?" 질의를 자기질문으로 확장해 HN·GDELT를 검색. 날짜는 반드시 출처의 날짜를 쓰고 LLM이 쓴 날짜는 버린다(CHRONOS의 날짜 오류 사례) |

### D. 예측과 외부 시각

| 연구 | 핵심 | 적용 |
|---|---|---|
| **LLM 예측 시스템** (Halawi·Zhang·Chen·Steinhardt, NeurIPS 2024) | 검색(질의 생성 → 뉴스 검색 → 걸러내기 → 요약) → 추론 → 여러 예측의 절사 평균. 사람 예측 집단 평균에 근접 | 관찰 지표의 가능성 판단을 **여러 번 샘플링해 절사 평균**. 결과는 확률이 아니라 ICD 203 단어 구간으로 표시(§6-3) |
| **구조화된 유추** (Green·Armstrong, IJF 2007) | 전문가가 유사 사례를 나열 → 유사도 평가 → 결과 대응. 정확도: 비구조 32% → 구조화 46% → 유추 2개 이상+직접 경험 60% | **P축 설계의 직접 근거.** 선례를 2개 이상 찾고, 유사도를 점수로 매기고, 선례의 결과를 대응시키는 3단계를 그대로 구현 |
| **참조 집단 예측·외부 시각** (Kahneman·Lovallo, Flyvbjerg) | 사례 안쪽 사정보다 비슷한 사례 집단의 실제 결과 분포에서 출발 | 보고서의 전망 문단은 **기저율 문장 먼저**, 사례 특수성 조정은 그다음. "이번은 다르다"는 근거를 요구 |

### E. 기술 인텔리전스와 미래연구

| 연구 | 핵심 | 적용 |
|---|---|---|
| **약신호** (Ansoff 1975; van Veer·Ortt 2021 정의 리뷰) | 처음엔 모호하다가 점점 출처·속성이 드러나는 위협·기회의 단서 | T축에서 "발언 → 논문 → 창업 → 대형 투자"로 신호가 강해지는 과정을 사다리로 보여 준다(약속 수준 연산) |
| **키워드 출현 지도·이슈 지도(KEM/KIM)** (Yoon 2012) | 빈도(중요도) × 문서 빈도(확산)로 약신호·강신호 구역 구분 | 레이더가 이미 비슷한 계산을 한다. 사건 레이어에서는 키워드 대신 **(유형, 대상) 쌍**으로 같은 지도를 그린다: "world-model × fund_raise"가 약신호 구역에서 강신호 구역으로 이동 |
| **스타 과학자 이동** (Zucker·Darby, 1996~2006) | 새 지식은 처음엔 사람에게 묻혀 있어 사람이 움직여야 이전된다. 스타 과학자의 기업 참여가 입지·IPO 시기·조달액과 연관 | **인물 축을 넣는 이론적 근거.** 핵심 인재 이동(depart·join·found)은 기술 상업화의 선행 지표로 별도 레이더 톤을 둔다(`talent_move`) |
| **수평선 탐색, 미래 바퀴, 교차 영향, 세 지평** (Glenn; Porter 2010 기술 예측 13계열) | 미래 바퀴: 한 변화의 1·2차 파급을 동심원으로. 교차 영향: 변화 쌍이 서로에게 주는 영향. 세 지평: 현재(H1)·전환(H2)·변혁(H3) | 사건 문서의 "So what" 단락을 **미래 바퀴 2단계**로 강제: 1차 파급(경쟁사·투자자) → 2차 파급(DX 제품·공급망). S축 주체들을 세 지평에 배치(H1 기존 LLM 강자, H2 하이브리드, H3 월드 모델 순수파) |

### F. 동향 보고서 작성 — 정보분석 작법

| 연구·표준 | 핵심 | 적용 |
|---|---|---|
| **구조화 분석 기법 — Tradecraft Primer** (미 정보공동체, 2009) | 인지 편향을 줄이는 기법: **핵심 가정 점검(KAC)**, 정보 품질 점검, **변화의 지표·이정표**, **경쟁 가설 분석(ACH: 반증 증거에 무게)**, 레드팀 | 사건 문서 생성 단계에 그대로 넣는다: 가정 3개 명시, 대안 가설 2~3개와 각 가설을 **반박하는** 증거, 관찰 지표, 반대 관점 1단락(기존 페르소나 중 '반대' 역할 재사용) |
| **ICD 203 분석 기준** (ODNI 2007, 2015 개정) | 근거 출처의 신뢰성 서술, **가능성(likelihood)과 확신도(confidence)를 분리**, 고정 확률 어휘(거의 없음 … 거의 확실), 사실과 가정·판단 구분. 2024 ODNI 연구노트: 한 문장에 가능성과 확신도를 섞으면 독자가 혼동 | ① 가능성은 7단계 고정 어휘(§6-3), 확신도는 근거 강도(B2 strength: strong/medium/weak)와 연결한 3단계. ② **같은 문장에 섞지 않는다.** ③ 문장마다 사실/판단 표시 |
| **BLUF·피라미드 원칙** (군·컨설팅 작법) | 결론 먼저, 근거는 아래로 | 사건 문서의 첫 줄 = 판단 한 문장 + 확신도. 1분 읽기 깊이(C1)에서는 이 줄만 |
| **세 확장 축과 보고서 목차의 대응** | — | §6-1 템플릿 |

### G. LLM 보고서 생성 연구

| 연구 | 핵심 | 적용 |
|---|---|---|
| **STORM / Co-STORM** (Shao 외, NAACL 2024; Stanford OVAL) | 좋은 보고서의 핵심은 **좋은 질문**. 비슷한 글에서 **관점**을 찾고, 관점별 가상 질의응답으로 질문 생성 → 개요 → 집필. 구성 +25%p, 범위 +10%p. 한계: 출처 편향 전이, 무관한 사실의 과잉 연결 | 우리의 31개 페르소나가 STORM의 관점에 해당. 확장 축(T·S·P·C·G)이 **질문 생성기** 역할: 축마다 고정 질문 템플릿(§5-5)을 두고 LLM은 답만 채운다. "과잉 연결" 한계 때문에 링크는 규칙으로 만들고 LLM이 새 연결을 지어내지 못하게 한다 |
| **DeepResearch Bench** (Du 외, 2025; ICLR 2026) | 보고서 품질(RACE: 포괄성·깊이·지시 준수·가독성)과 **인용 신뢰도(FACT: 유효 인용 수, 인용 정확도)** | 평가(§8)를 이 두 축으로: 사건 문서 표본의 주장-인용 쌍을 뽑아 근거 기사가 실제로 뒷받침하는지 판정 |
| **CHRONOS, Halawi** (위) | 반복 자기질문 검색, 검색-추론-집계 | §5-4 백필, §6-3 가능성 판단 |

### 조사에서 얻은 설계 원칙 (요약)

1. **닫힌 사건 유형 + 양태 칸**(PLOVER) — 집계·기저율이 가능해야 인사이트가 된다.
2. **개체는 레지스트리 키로 고정**(SemEval TimeLine의 오류 전파 교훈) — 인물 레지스트리를 새로 둔다.
3. **이중 시간·무효화**(Graphiti) — 과거를 지우지 않는다.
4. **단순한 구조가 더 정확**(Story Forest) — 사건 연결은 나무, 인과 자동 생성 금지.
5. **질문 템플릿이 보고서 품질을 정한다**(STORM) — 축별 고정 질문.
6. **외부 시각 먼저**(구조화된 유추, 참조 집단) — P축 기저율을 전망 앞에.
7. **사실·가정·판단 분리, 가능성·확신도 분리**(Tradecraft, ICD 203).
8. **빈도·최근성 기준선과 비교**(Lee 외 2023) — LLM 판단이 기준선과 같으면 새 정보가 없는 것.
9. **비용은 후보 축소로**(LLM-TLS 토큰 비용, 공참조의 제곱 비용).

---

## 3. 현재 시스템의 출발점과 공백

| 있는 것 | 위치 | 확장 분석에서의 역할 |
|---|---|---|
| 기사 30.7만 건(2026-10-03~), 카드 29.1만 장 | `items`, `item_cards` | 사건 근거 |
| 이슈(같은 사건 보도 묶음) 21.8만 개, 7일 다출처 이슈 7,823개 | `stories` | 사건 추출 단위(이슈 대표 기사) |
| 카드 분류: 테마·signal_type 10종·impact·scope·relevance | `item_cards` | 사건 유형의 상위 범주·후보 선정 |
| 기업 471곳·별칭 1,553개, 관계(self/competitor/supplier/partner/peer) | `companies` | 주체·대상 개체, DX 연결 |
| 기술 레지스트리 | `technologies` | 대상 B(기술) 개체 |
| 교차 식별자(arXiv·DOI·GitHub) | `item_refs` | 논문·코드 사건, 연구 → OSS 시차 |
| 다국어 임베딩(bge-m3) + LLM 병합 판정 | `stories/semantic.py` | 사건 공참조에 재사용 |
| 기업 레이더: 테마 진입·신흥 업체·동시 언급 쌍 | 계획 12 | S축의 통계 부분 재사용 |
| 브리핑 연속성(B1)·근거 강도(B2)·페르소나 31개·관점 충돌 | 계획 13 | 궤적 판정·확신도·관점 |
| 주제 파일(키워드·기업·노드·의미 문장 조건, 가설·찬반 근거) | 계획 16 #4 | 주제 정의와 근거 묶음. R1 보고서가 주제 파일에서 시작할 수 있음 |
| 카드 임베딩(bge-m3, pgvector) 의미 검색 | 계획 16 #1 | 주제 문장 → 근거 카드 |
| 투자·인수·제휴 추출(주체·상대·금액·날짜, Qwen 야간) | 계획 16 #8 `deals` | **사건 레이어의 일부가 이미 있음**: X2는 이 추출을 24종 유형·양태로 일반화 |
| 보고서 문서 모델(Markdown·Word·PowerPoint) | 계획 16 #11 | R1 보고서 내보내기 |

| 공백 | 실측 근거 | 설계 대응 |
|---|---|---|
| **인물 축 없음** | 카드 프롬프트가 "인물은 넣지 않는다"(`cards/schemas.py:183`). 르쿤은 제목 문자열로만 존재 | X1 인물 레지스트리 + 카드 분류에 `people` 칸 |
| **이슈 ≠ 사건** | 르쿤 82건이 16개 이슈. 10/12 방한 발언 6개, 10/03~05 위험론 발언 4개 이슈로 분산 | X2 사건 레이어: (유형, 주체, 대상, ±7일)로 이슈 위에서 다시 묶음 |
| **구조화 사건 없음** | signal_type은 기사 단위 10종. "누가 누구를 떠나 무엇을 세웠다"를 표현 못 함 | X2 `events` + `event_args` |
| **과거가 없음** | 수집 시작이 2026-10-03. 르쿤의 Meta 시절·퇴사(2025-11)·시드(2026-03)는 코퍼스 밖 | X3 필요할 때만 백필(Wikidata·OpenAlex·GitHub·HN) |
| **미래 표현이 사실과 섞임** | "~할 계획", "~설"을 구분하는 칸 없음 | 양태(mode) 칸 + `expectations` |
| **개체 레지스트리 공백** | 월드 모델 기사 172건 중 154건 기업 키 없음. AMI Labs(12장)·World Labs(30장 이상)·Thinking Machines 미등록 | 사건 추출이 원문 표기를 남기고, 신흥 업체 후보 대기열(계획 12 §3-2-5)로 보냄 |
| **사건 시각 = 수집 시각** | 집계 기준이 `first_seen_at` | 사건 시각(event_time·정밀도)과 기록 시각 분리 |

---

## 4. 데이터 모델

그래프 DB를 새로 들이지 않는다. 단일 서버·PostgreSQL 16에서 개체는 기존 레지스트리를 유지하고, 다형 참조 문자열 `kind:key`로 연결한다(`company:meta`, `person:yann-lecun`, `tech:jepa`, `theme:ai__foundation_model`, `region:kr`). 2-hop 확장은 재귀 CTE로 충분하다.

### 4-1. 인물 레지스트리 (`catalog/people.yaml` → `people`, `person_aliases`)

| 필드 | 뜻 |
|---|---|
| `key` | 정규화 키(`yann-lecun`) |
| `name` / `name_ko` | 공식 표기 / 한국어(얀 르쿤) |
| `roles` | `researcher` · `founder` · `executive` · `investor` · `policymaker` · `engineer` |
| `wikidata_qid`, `openalex_author_id`, `orcid`, `github` | 동명이인 구분과 백필 열쇠(공개 학술·업무 식별자만) |
| `watch` | `core`(항상 확장) · `normal` · `candidate`(승격 전) |
| `themes` | 관련 테마 1~4개 |
| `aliases` | 표기 변형(Yann LeCun, 얀 르쿤, LeCun, 르쿤) — 성만 단독 별칭은 흔하지 않은 성일 때만 |

- 범위: **공적 역할로 보도되는 인물만**(빅테크·AI 랩 리더, 수석 과학자, DX 경쟁사·공급사 경영진, 규제기관 책임자, 주요 창업자). 시작 약 300명. 사생활 정보(가족·주소·개인 SNS)는 저장하지 않는다. 직업 활동과 공개 발언만.
- 현재 소속은 레지스트리에 두지 않는다. 시간에 따라 변하므로 `entity_states`(§4-4)가 원천이다.

### 4-2. 사건 (`events`, `event_args`)

```
events
  id               bigint PK
  type             str_enum (§4-2-1, 24종)
  mode             str_enum: asserted | ongoing | planned | expected | rumored | hypothetical | negated | cancelled
  event_date       date            -- 사건이 일어난(일어날) 날
  date_precision   day | month | quarter | year
  date_basis       explicit | relative_resolved | published_fallback
  recorded_at      timestamptz     -- 우리가 처음 안 시각(이중 시간의 두 번째 축)
  summary_ko       text            -- 한 문장, 근거 기사에서만
  salience         smallint 0~100  -- 확장 대상 선정용(§5-5)
  confidence       real            -- 추출 신뢰도
  source_kind      corpus | wikidata | openalex | github | hn | gdelt | manual
  extractor        text            -- 모델·프롬프트 버전
  merged_into      bigint NULL     -- 공참조로 흡수되면 대표 사건 id
  review           pending | ok | fixed | rejected
event_evidence (event_id, item_id | external_url, story_id, quote_span)   -- 근거
event_args
  event_id, role, ref (kind:key) NULL, text (원문 표기), amount numeric NULL, currency NULL
  role ∈ agent | patient | origin | result_org | partner | investor | acquirer | target
       | tech | theme | product | market | location | regulator | amount
```

#### 4-2-1. 사건 유형 (닫힌 목록, 24종)

기존 `signal_type`(10종)을 상위 범주로 두고 그 아래를 나눈다. 카드 화면과 레이더 호환을 위해 매핑을 고정한다.

| 상위(signal_type) | 사건 유형 | 필수 역할 | 약속 사다리 단계 |
|---|---|---|---|
| (인물) market | `join` 합류 · `depart` 퇴사·사임 · `found` 창업 | agent(person), origin/result_org | 4 |
| research | `publish` 논문·벤치마크 · `state` 공개 발언·입장(stance 포함) | agent, tech | 2 / 1 |
| ecosystem | `open_source` 코드·가중치 공개 · `award` 수상 | agent, tech | 3 |
| launch | `preannounce` 출시 예고 · `launch` 출시 | agent, product/tech | 4 / 6 |
| finance | `fund_raise` 투자 유치 · `invest` 투자 집행 · `capex` 설비 투자 | agent, amount | 5 |
| market | `acquire` 인수 · `partner` 제휴 · `license_deal` 라이선스·인재 인수형 거래 · `hire_key` 핵심 인재 영입 · `reorg` 조직 개편·감원 · `market_enter` / `market_exit` | agent, patient/partner | 5~7 |
| supply | `supply_deal` 공급 계약 | agent, partner | 5 |
| ip | `patent` · `litigate` | agent, patient | 3 |
| regulation | `regulate` 규제 조치 · `comply` 대응 | regulator/agent | — |
| standard | `standardize` | agent, tech | 3 |
| security_event | `incident` | agent | — |

`stance`(`state` 사건): `{topic: tech/theme 키 또는 짧은 명사구, position: support | oppose | caution | neutral}`. 입장 지도(§1-3)의 재료.

### 4-3. 사건 연결 (`event_links`)

```
event_links (from_id, to_id, relation, score, method, created_at)
relation ∈ continues     -- 같은 주체의 다음 단계(사건 진화 그래프 점수)
         | escalates     -- 같은 주체·대상에서 약속 사다리 상승
         | reverses      -- 반대 방향(예: 출시 → 철회, 지지 → 반대)
         | responds_to   -- 상대방 축: 다른 주체가 시간상 뒤에, 같은 대상·상대로
         | subevent_of   -- 큰 사건의 일부(방한 → 강연·인터뷰들)
         | same_pattern  -- 유사 사례 축(유형·역할 구조가 같음)
method ∈ rule | llm_judge | manual
```

인과(`causes`)는 두지 않는다. `responds_to`도 "시간상 뒤 + 같은 상대·대상"이라는 **규칙만으로** 만들고 화면에는 "뒤이은 움직임"으로 쓴다.

### 4-4. 개체 상태 (`entity_states`, 이중 시간)

```
entity_states
  subject (kind:key), attribute, value_ref (kind:key) NULL, value_text NULL,
  valid_from date NULL, valid_to date NULL, precision,
  source_kind, source_ref (event_id | wikidata 진술 id | openalex work id),
  recorded_at timestamptz, invalidated_at timestamptz NULL, invalidated_by bigint NULL
attribute ∈ affiliation | role_title | founded | board_seat | investor_in | hq_region | stance:<topic>
```

- `depart`·`join`·`found` 사건이 확정(asserted, review≠rejected)되면 상태를 자동으로 열고 닫는다.
- 모순되는 새 사실은 이전 행을 **무효화**하고 지우지 않는다. "2026-10-05 브리핑 시점에 시스템이 믿던 르쿤의 소속"을 재현할 수 있다.

### 4-5. 기대·관찰 지표 (`expectations`)

```
expectations
  id, subject (kind:key), expected_type, expected_args jsonb,
  due_from date, due_to date,
  origin: planned_event (mode=planned/expected) | schema_next_step | analyst
  source_event_id, likelihood_word (ICD 203 어휘), likelihood_p real,
  status: pending | met | missed | superseded | withdrawn,
  resolved_by_event_id NULL, resolved_at NULL
```

- 원천 세 가지: ① 기사의 계획·예고 문장(양태 `planned`/`expected`), ② 사건 유형 스키마의 전형적 다음 단계(§5-6), ③ 분석가가 콘솔에서 추가.
- 새 사건이 들어오면 `pending` 기대와 (주체, 유형) 일치 여부를 보고 `met`으로 닫는다. 기한이 지나면 `missed`. → 브리핑 B1 연속성의 "예고했던 것이 실제로 일어났나"와 **성적표**(§6-4).

### 4-6. 사건 문서 캐시 (`event_dossiers`)

```
event_dossiers (event_id, built_at, window_from, window_to, axes jsonb, narrative jsonb,
                citations jsonb, model, cost_tokens, quality jsonb)
```

확장 질의 결과(T·S·P·C·G)와 생성된 서술을 저장한다. 같은 사건은 새 근거가 없으면 다시 만들지 않는다.

### 4-7. 카드 분류 변경

- `Classification.people`(최대 3): 기사의 주체이거나 직접 대상인 **인물** 공식 표기. 기존 `companies` 규칙 문구에서 "인물은 넣지 않는다"는 유지하고 인물은 이 칸으로 간다.
- `item_cards.person_keys`: `companies` → `company_keys`와 같은 트리거 방식.
- 프롬프트 증가는 한 줄. 카드 엔진 비용 영향은 미미하다.

---

## 5. 파이프라인

```
수집 → 카드(분류 + people) → 이슈 묶기 ──┐
                                          ▼
                 X2 사건 추출(이슈 대표, 하루 600~1,500, 로컬 Qwen, 00~04시 32k 컨텍스트)
                                          ▼
                 X2 사건 공참조(같은 유형·주체·대상 ±7일 → LLM 판정) → merged_into
                                          ▼
                 X3 상태 갱신(entity_states) · 기대 생성/해소(expectations) · 규칙 링크(event_links)
                                          ▼
                 X5 확장 대상 선정(salience) → X4 확장 질의 T·S·P·C·G (+ X3 필요 시 백필)
                                          ▼
                 X5 사건 문서(dossier) → 04:40 스냅숏 → 05:00 브리핑(Claude)·주간/월간 동향 보고서
```

### 5-1. 후보 선정 (비용 상한)

실측(최근 7일 평균): 관련도 60 이상·출처 2곳 이상 이슈가 **하루 약 556개**, 관련도 80 이상 이슈가 하루 약 2,003개.

| 등급 | 조건 | 하루 예상 |
|---|---|---|
| A | 관련도 ≥ 60 그리고 출처 ≥ 2 | ~560 |
| B | 관련도 ≥ 60 그리고 (`person_keys`에 watch=core 인물 또는 `company_keys`에 relation ∈ self/competitor/supplier/partner) | +300~800 |
| C | 나머지 관련도 ≥ 80 단일 출처 | 여유분이 있을 때만 |

자사 채널(기업 `domains`와 소스 도메인 일치) 이슈는 사건으로 추출하되 `source_kind` 표시를 남겨 S축 집계에서 별도로 센다(계획 12의 자사 발표 부풀림 교훈).

### 5-2. 사건 추출 (X2)

- 입력: 이슈 대표 기사의 원제목·카드 제목·요약(최대 3줄)·발행일·소스 이름 + 같은 이슈의 다른 기사 제목 최대 3개 + 카드의 `company_keys`·`person_keys`·`technology_keys`(후보 개체 목록).
- 엔진: 로컬 Qwen(카드 엔진의 Qwen 레인 재사용). 8개 이슈를 한 번에, JSON 스키마 강제. 밤(00~04시, 32k 컨텍스트)에 몰아서, 낮에는 A등급만 소량.
- 프롬프트 규칙(요지):
  ```
  각 이슈의 주된 사건 1개(최대 2개)를 뽑는다.
  type: 목록 중 하나. 맞는 것이 없으면 사건을 만들지 않는다.
  mode: 이미 일어난 일만 asserted. "~할 계획/예정"=planned, 제3자 전망=expected,
        익명 소식통·"~설"=rumored, 부인=negated. 모르면 asserted로 쓰지 말고 rumored.
  args: 후보 개체 목록의 키를 우선 쓰고, 없으면 원문 표기를 text로.
  date: 본문에 날짜가 있으면 그 날짜와 정밀도. "지난달" 같은 상대 표현은 발행일 기준으로 환산하고
        date_basis=relative_resolved. 없으면 발행일, date_basis=published_fallback.
  summary_ko: 입력에 있는 사실만 한 문장.
  ```
- 검증(코드): 필수 역할 누락·역할 개체 종류 불일치(예: `found`의 agent가 기술)·미래 날짜인데 `asserted` → 버리거나 `rumored`로 낮춤. 숫자 금액은 원문에 있는 값만(카드 보존 검사 `cards/preserve.py` 재사용).
- 고가치 사건(salience ≥ 80, 인물 사건)은 두 번 추출해 유형·양태가 같을 때만 확정, 다르면 콘솔 검토 큐.

### 5-3. 사건 공참조 (이슈 위에서 다시 묶기)

- 후보: 같은 `type` 상위 범주 + agent 키 동일 + (대상 키 하나 이상 공유 또는 `state` 사건이면 stance topic 동일) + 날짜 차이 ≤ 7일.
- 판정: 기존 `stories/semantic.py`의 LLM 판정 방식(쌍, 한 번만 묻기 — `StoryMergeCheck`와 같은 장부)을 사건 쌍에 적용.
- 르쿤 실측 사례: 10/12 방한 관련 6개 이슈 → `subevent_of` 방한(1개 상위 사건) 아래 강연·인터뷰 하위 사건들. 10/03~05 위험론 4개 이슈 → `state(stance: ai_existential_risk = oppose)` 1개 사건 + 근거 기사 다수.

### 5-4. 과거 백필 (X3, 필요할 때만)

코퍼스가 10일치라 T축 과거와 P축 선례는 외부에서 가져와야 한다. **전량 수집이 아니라 확장 대상 개체에 대해 필요할 때만** 가져오고 캐시한다.

| 출처 | 가져오는 것 | 비용·제약 |
|---|---|---|
| **Wikidata** (SPARQL, 무료) | 인물: 고용주(P108)+시작·종료(P580/P582), 창립자(P112), 수상(P166). 조직: 설립(P571), 창립자, 모회사(P749), 인수 | 하루 상한 200질의, 결과 30일 캐시. QID로 동명이인 해결 |
| **OpenAlex** (저자·저작) | 연도별 논문·주제 변화, 소속(`affiliations`는 최근 약 10년, `years` 포함) | **운영 서버는 키 없이 공유 일일 한도를 쓴다.** 대량 탐색 금지, 개체당 2~3호출, 하루 상한 50호출 |
| **GitHub** | 조직·인물 저장소 생성·첫 공개 시점(open_source 사건) | 기존 토큰 예산 공유 |
| **HN Algolia** (기간 검색) | 이름·조직의 과거 화제 사건(날짜 정확) | 무료, 기존 공유 예산 |
| **GDELT DOC API** (선택) | 최근 수개월 전 세계 보도량·첫 보도 국가 | 무료, 기간 제한. G축 보조 |
| **우리 코퍼스** | 2026-10-03 이후 전부 | — |

- 백필 사건은 `source_kind`가 corpus가 아니고 화면에 **"수집 이전(외부 출처)"** 배지를 단다. 근거는 출처 URL·진술 ID.
- CHRONOS식 자기질문: "르쿤의 과거 주요 사건" → 질의 확장("LeCun Meta FAIR founded", "LeCun JEPA paper", "LeCun leaves Meta")을 LLM이 만들고 HN·Wikidata로 검색. **날짜는 출처의 것만 쓴다.**
- LLM의 배경지식은 사건으로 저장하지 않는다. 사건 문서에서 쓸 때는 "모델 배경지식(검증 전)"으로 따로 표시하고 브리핑 본문에는 넣지 않는다(시간 누수·환각 방지).

### 5-5. 확장 질의 (X4) — 축별 질의와 고정 질문

확장 대상: 하루 salience 상위 20개 사건 + core 인물·self/competitor 기업의 모든 사건. salience = 규모(금액·출처 수) + DX 관계 + 신규성(궤적 기준선과 다름) + 약속 단계 상승.

| 축 | 질의(요지) | 고정 질문(STORM의 관점 질문에 해당) |
|---|---|---|
| **T** | `events ⨝ event_args WHERE ref = agent ORDER BY event_date` (병합된 사건 제외), `entity_states` 이력, `expectations WHERE subject = agent` | ① 이 사건 전 주체의 직전 3개 사건은? ② 이번 사건은 연속·격상·전환·역전 중 무엇? ③ 주체가 예고했고 아직 안 일어난 일은? ④ 입장이 바뀐 적이 있나? |
| **S** | 같은 `tech`/`theme` 인자를 가진 다른 agent의 사건(기본 180일 + 백필), 주체별 첫 진입일·최근 사건·누적 금액·유형 분포; 기업 레이더의 테마 점유와 결합 | ① 같은 대상을 누가 하나(빅테크/독립/연구기관/국내)? ② 누가 먼저 들어왔고 이번 주체는 몇 번째? ③ 방식 차이(연구형·제품형·오픈소스)? ④ 최근 90일 새로 들어온 주체는? |
| **P** | 같은 유형 + 같은 역할 구조(예: `found` ∧ agent.roles∋researcher ∧ origin.kind=bigtech)의 사건과 각 결과 조직의 이후 24개월 사건 | ① 선례 2개 이상과 유사도 점수 ② 선례들은 어떻게 끝났나(결과 분포) ③ 이번이 다른 점은? |
| **C** | origin·partner·patient 개체의 사건 중 이번 사건 이후 | ① 떠난/상대 쪽은 무엇을 했나 ② 같은 대상 기술을 계속하나 |
| **G** | 근거 기사의 소스 지역·언어별 첫 보도 시각, location 인자 | ① 어디서 먼저 보도? ② 국내 보도 시차·공백? ③ 한국 관련 언급(방한, 국내 파트너)? |

모든 축 결과에 **빈도·최근성 기준선**을 함께 붙인다(예: 이 주체의 월평균 사건 수, 이 대상의 월평균 신규 진입자 수). LLM 판단이 기준선과 같으면 "새 정보 없음"으로 본다.

### 5-6. 다음 단계 스키마 (관찰 지표 후보)

유형별 전형적 다음 단계를 작게 둔다(Dror 외의 스키마 유도를 콘솔에서 사람이 다듬는 방식):

| 사건 | 전형적 다음 단계(기한) |
|---|---|
| `found`(연구자 창업) | 핵심 인재 영입(3개월) → 시드/시리즈 A(6~12개월) → 첫 모델·논문 공개(6~12개월) → 산업 파트너(12개월) → 라이선스·인수형 거래 또는 제품(24개월) |
| `fund_raise` | 채용 확대·거점 개설(6개월) → 첫 제품/모델(12개월) |
| `preannounce` | `launch`(예고 시기) 또는 연기 |
| `acquire` | 규제 심사(`regulate`) → 통합·제품 변경 |
| `depart`(빅테크 핵심 인물) | 출발지 `reorg`/`hire_key`(3개월) |

선례(P축)가 쌓이면 각 단계의 실제 도달 비율로 기한·가능성을 보정한다(TLogic식 규칙 신뢰도).

---

## 6. 보고서 적용

### 6-1. 사건 확장 카드(사건 문서) 템플릿

| 단락 | 내용 | 근거 연구 |
|---|---|---|
| **판단(BLUF)** | 한 문장 판단 + 확신도(높음/보통/낮음) | 피라미드, ICD 203 |
| **무슨 일인가** | 4W 사실, 양태 표시, 근거 기사 | 5W1H, PLOVER mode |
| **A의 궤적** | 직전 사건 3~5개 타임라인, 궤적 판정(연속·격상·전환·역전), 약속 사다리 위치 | SemEval TimeLine, EventKG 전기, 약신호 |
| **B의 지형** | 같은 대상의 주체 노선도, 진입 순서, 방식 차이, 세 지평 배치 | Metro maps, 세 지평, 기업 레이더 |
| **선례와 기저율** | 선례 2개 이상·유사도·결과 분포 → "외부 시각" 한 문장 | 구조화된 유추, 참조 집단 |
| **상대방·지역** | 출발지·상대의 뒤이은 움직임, 지역 시차·국내 공백 | 사건 진화 그래프, G축 |
| **So what (DX)** | 미래 바퀴 2단계: 1차 파급 → 2차 파급, 페르소나별 기회·위험(기존 B6 구조) | 미래 바퀴, 페르소나 |
| **핵심 가정 · 대안 가설** | 가정 3개, 대안 가설 2~3개와 각 가설을 **반박하는** 증거 | KAC, ACH |
| **관찰 지표** | 기한 있는 기대 3~5개, ICD 203 가능성 어휘 | Indicators, ICD 203, Halawi |

르쿤 사례의 BLUF 예(근거가 쌓였을 때의 모양):

> **판단:** AMI Labs는 르쿤이 2022년부터 주장한 JEPA 노선의 상업화이며(연속·격상), 월드 모델 분야는 10억 달러급 독립 진입자 2곳과 빅테크 3곳이 맞붙는 초기 경쟁 단계다. 삼성은 투자자로 연결되어 있다. *(확신도: 보통 — 핵심 사실은 다출처, 경쟁 구도는 백필 근거 포함)*
> **외부 시각:** 빅랩 핵심 인물 창업 선례 6건 중 3건이 2년 안에 빅테크의 라이선스·인재 인수형 거래로 끝났다.
> **관찰 지표:** AMI 첫 공개 모델(12개월 안, *가능성 높음*), 제조·로봇 산업 파트너 발표(*반반*), 삼성과의 협력 공개(*가능성 낮음~반반*).

(수치와 가능성 단어는 예시이며 실제 값은 X4·X6가 계산한다.)

### 6-2. 어디에 들어가나

| 산출물 | 적용 |
|---|---|
| **일간 브리핑**(05:00) | 상위 3개 사건에 "확장 분석" 패널. 5분 읽기 깊이는 판단·궤적·지형 한 줄씩, 깊이 읽기는 전체. B1 연속성 판정을 제목 비교 대신 **사건 링크**(`continues`/`escalates`)로 |
| **주간·월간 동향 보고서** | 장 구성: ① 이번 기간 핵심 사건(판단 먼저) ② 주요 주체 궤적(core 인물·경쟁사) ③ 대상별 지형 변화(새 진입자·리더 교체) ④ 선례에서 본 전망 ⑤ 관찰 지표 성적표(§6-4) ⑥ 다음 기간 관찰 목록 |
| **인물 페이지**(신규) | 타임라인(수집 이전 배지 포함), 소속 이력, 입장 지도, 기대 목록 |
| **기업·기술 상세** | 기업: 사건 타임라인 + 상대방 축. 기술: 주체 노선도(S축) |
| **레이더 톤 추가** | `talent_move`(core 인물 depart/join/found), `commitment_up`(약속 사다리 2단계 이상 상승), `new_entrant_event`(대상 B에 새 주체 첫 사건), `expectation_met`/`expectation_missed` |
| **페르소나** | 페르소나 입력에 사건 문서를 넣어 관점별 relevance·stance가 확장 결과를 근거로 하게 함 |

### 6-3. 확률·확신도 표현 규칙 (ICD 203 준용)

| 어휘 | 구간 |
|---|---|
| 거의 없음 | 1~5% |
| 매우 낮음 | 5~20% |
| 낮음 | 20~45% |
| 반반 | 45~55% |
| 높음 | 55~80% |
| 매우 높음 | 80~95% |
| 거의 확실 | 95~99% |

- 가능성: 관찰 지표에만. LLM 판단 5회 샘플의 절사 평균(Halawi) + 선례 기저율과의 차이를 함께 저장.
- 확신도: B2 근거 강도와 연결(strong → 높음, medium → 보통, weak → 낮음). 백필 근거만 있으면 한 단계 낮춤.
- **한 문장에 가능성과 확신도를 함께 쓰지 않는다.**

### 6-4. 관찰 지표 성적표

- 매주: 기한이 지난 기대의 met/missed 집계, 가능성 어휘별 적중률(보정 곡선), 브라이어 점수.
- 성적표가 낮은 사건 유형·스키마는 기한·가능성을 낮춰 보정한다. 보고서 신뢰도를 독자가 직접 확인하게 한다.

---

## 7. 화면

- **사건 확장 카드**: 상단 BLUF, 아래 탭 `궤적 | 지형 | 선례 | 상대·지역 | 관찰 지표`. 각 문장의 근거 칩은 기존 카드 링크 규칙.
- **궤적 타임라인**: 가로 시간축, 사건 점은 약속 사다리 높이(발언 낮음 → 투자·출시 높음)로 배치해 "격상"이 눈에 보이게. 수집 이전 구간은 회색 배경.
- **지형 노선도**: 노선 = 주체, 역 = 사건, 색 = 관계(self/competitor/…), 갈아타는 역 = 공동 사건(투자·제휴).
- **인물 페이지**: 타임라인 + 소속 이력 막대 + 입장 지도.
- **콘솔**: 사건 검토 큐(표본 정밀도), 인물 후보 승격, 다음 단계 스키마 편집, 기대 수동 추가.

---

## 8. 평가

| 대상 | 지표 | 목표(초기) | 방법 |
|---|---|---|---|
| 사건 추출 | 유형·역할·양태 정밀도 | 유형 ≥ 0.85, 양태 ≥ 0.90, 날짜(정밀도 내) ≥ 0.80 | 주 100건 표본 콘솔 검토 |
| 사건 공참조 | 병합 정밀도·재현율 | P ≥ 0.9 | 르쿤처럼 흩어진 실측 사례 30개 정답셋 |
| 궤적(T) | 알려진 이정표 재현율 | core 인물 30명, Wikidata 주요 이정표의 70% | Wikidata 대비 |
| 지형(S) | 주요 주체 재현율 | 10개 테마, 분석가 목록 대비 상위 10의 70% | 수작업 목록 |
| 사건 문서 | 인용 정확도(FACT), 품질(RACE식 4항목) | 인용 정확도 ≥ 0.9 | 주장-인용 쌍 표본 LLM 판정 + 사람 확인 |
| 관찰 지표 | 브라이어 점수, 보정 곡선 | 기준선(빈도 규칙)보다 낮을 것 | 성적표 |
| 비용 | Qwen 시간·토큰/일, Claude 토큰 증가분 | Qwen 야간 4시간 안, Claude 브리핑 입력 +20% 이하 | 실행 기록 |

---

## 9. 단계 (PR 단위)

- [x] **R1 주제 요청 보고서** (이번 PR, §12) — 리더 `/reports`에서 주제·정보·기간으로 요청, 호스트 launchd가 Claude Opus로 검색 계획 → 근거 → 작성 → 인용 검증 → HTML. 주제 파일에서 바로 시작, Markdown·Word·PowerPoint·HTML 내보내기.
- [ ] **X1 인물 레지스트리와 카드 인물 태그** — `catalog/people.yaml`(~300명, QID·OpenAlex ID), 마이그레이션(people·person_aliases, item_cards.people·person_keys + GIN + 트리거, 키워드 기반 백필), `Classification.people`, `news-insight people seed|candidates`, 리더 필터 `?person=`.
- [ ] **X2 사건 추출·공참조** — `deals` 추출(계획 16 #8)을 일반화한다. 마이그레이션(events·event_args·event_evidence·event_links), 유형·양태 enum, 후보 선정 A/B, Qwen 추출(배치 8, JSON 스키마), 검증, 사건 쌍 판정 장부, `news-insight events extract|merge|review`, 테스트(르쿤 실측 이슈 16개 고정 픽스처).
- [ ] **X3 상태·백필** — entity_states(이중 시간·무효화), depart/join/found → 상태 자동 갱신, Wikidata·OpenAlex·GitHub·HN 백필 어댑터(하루 상한·캐시, OpenAlex 공유 예산 준수), "수집 이전" 표시.
- [ ] **X4 확장 API** — `/events/{id}/expand?axes=T,S,P,C,G`, salience, 축별 질의 + 기준선, 인물·기업·기술 상세용 타임라인 API.
- [ ] **X5 사건 문서와 브리핑 통합** — dossier 생성(04:40 스냅숏 단계), 다이제스트 번들에 상위 3개 사건 문서, Claude 프롬프트에 §6-1 템플릿·ICD 203 규칙, B1 연속성의 사건 링크 전환, 페르소나 입력 확장.
- [ ] **X6 관찰 지표와 성적표** — expectations, 다음 단계 스키마(콘솔 편집), 해소 규칙, 주간 성적표, 레이더 톤 5종.
- [ ] **X7 웹** — 사건 확장 카드, 궤적 타임라인, 지형 노선도, 인물 페이지, 콘솔 검토 큐.
- [ ] **X8 평가 도구** — 표본 추출·정답셋·인용 판정·브라이어 계산, 주간 리포트.

순서 근거: X1·X2 없이는 아무 축도 계산할 수 없고, X3 없이는 T·P축이 10일치에 갇힌다. X4~X5가 사용자 가치의 핵심이고, X6은 신뢰(보정)를, X7은 탐색을 더한다.

---

## 10. 위험과 주의

| 위험 | 대응 |
|---|---|
| 과거가 짧다(10일) | 백필 + "수집 이전" 배지. 기저율은 선례가 5건 미만이면 문장으로 쓰지 않고 "선례 부족"으로 표시 |
| 동명이인·모호한 이름(Meta, 흔한 성) | QID·레지스트리 키로만 연결. 성 단독 별칭 금지 |
| LLM 환각·시간 누수 | 사실은 DB 사건에서만, 날짜는 출처에서만, 모델 배경지식은 별도 표시·본문 제외 |
| 인과의 과장 | 인과 링크 없음. "뒤이은 움직임"·"선후"로만 서술 |
| 자사 채널 부풀림 | 자사 발표 사건을 S축 집계에서 분리(계획 12) |
| LLM 한도 | 추출은 로컬 Qwen(야간 32k). Claude는 기존 05:00 브리핑 한 번에 사건 문서만 추가. 카드 엔진에 Claude를 쓰지 않는다(2026-10-07 결정) |
| OpenAlex 공유 한도 | 키 없는 운영 환경: 개체당 2~3호출, 하루 50호출 상한, 대량 탐색 금지 |
| 인물 정보의 민감성 | 공적 역할 인물만, 직업 활동·공개 발언만. 사생활 속성 칸을 만들지 않는다 |
| 자동 판단 과신 | 모든 판단에 확신도·가정·대안 가설을 붙이고 성적표로 검증 |

---

## 11. 참고 문헌과 출처

**사건 추출·표현**
- Hamborg, Breitinger, Gipp. *Giveme5W1H: A Universal System for Extracting Main Events from News Articles.* INRA 2019. [KOPS](https://kops.uni-konstanz.de/entities/publication/e8c35543-4afb-42cd-aa07-e678e91f381e), [PyPI](https://pypi.python.org/project/giveme5w1h/1.0.4/)
- Open Event Data Alliance. PLOVER 코드북; Halterman 외, *PLOVER and POLECAT* (ISA 2023). [CAMEO 개요](https://en.wikipedia.org/wiki/Conflict_and_Mediation_Event_Observations), [Creating Custom Event Data Without Dictionaries](https://arxiv.org/pdf/2304.01331)
- Singhania 외. *Neon: News Entity-Interaction Extraction for Enhanced Question Answering.* 2024. [arXiv 2411.12449](https://arxiv.org/abs/2411.12449v1)
- Wang 외. *MAVEN-ERE.* EMNLP 2022. [arXiv 2211.07342](https://alphaxiv.org/abs/2211.07342)
- Min 외. *Synergetic Event Understanding: Cross-Document Event Coreference with LLMs.* ACL 2024. [ACL Anthology](https://aclanthology.org/2024.acl-long.164)
- Dror, Wang, Roth. *Zero-Shot On-the-Fly Event Schema Induction.* EACL 2023 Findings. [arXiv 2210.06254](https://arxiv.org/pdf/2210.06254)
- *Event Extraction in Large Language Model* (2025 입장·서베이). [arXiv 2512.19537](https://arxiv.org/html/2512.19537v1); *Event-Centric Temporal Knowledge Graph Construction: A Survey* (Mathematics 2023). [DOI](https://doi.org/10.3390/math11234852)

**시간 지식그래프·예측**
- Gottschalk, Demidova. *EventKG.* ESWC 2018. [arXiv 1804.04526](https://arxiv.org/pdf/1804.04526); 전기 타임라인 저널판 [SWJ](https://www.semantic-web-journal.net/system/files/swj2084.pdf)
- Rasmussen 외. *Zep: A Temporal Knowledge Graph Architecture for Agent Memory.* 2025. [arXiv 2501.13956](https://arxiv.org/html/2501.13956v1), [Graphiti (Neo4j)](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/)
- Liu 외. *TLogic.* AAAI 2022. [arXiv 2112.08025](https://arxiv.org/pdf/2112.08025)
- Lee 외. *Temporal Knowledge Graph Forecasting Without Knowledge Using In-Context Learning.* EMNLP 2023. [ACL Anthology](https://aclanthology.org/2023.emnlp-main.36)
- 시간 인식 GraphRAG: TG-RAG [arXiv 2510.13590](https://arxiv.org/html/2510.13590v1), STAR-RAG [arXiv 2510.16715](https://arxiv.org/abs/2510.16715), T-GRAG [arXiv 2508.01680](https://arxiv.org/abs/2508.01680v1), DyG-RAG [arXiv 2507.13396](https://arxiv.org/abs/2507.13396v1)

**타임라인·이야기 구조**
- Minard 외. *SemEval-2015 Task 4: TimeLine: Cross-Document Event Ordering.* [과제 페이지](https://alt.qcri.org/semeval2015/task4), [논문](https://adimen.ehu.eus/~rigau/publications/SemEval15-TimeLines-task.pdf)
- Yang, Shi, Wei. *Discovering Event Evolution Graphs from News Corpora.* IEEE SMC-A 2009. [WWW 2006 예비판](https://archives.iw3c2.org/www2006/programme/files/pdf/p134.pdf)
- Shahaf 외. *Trains of Thought* / *Information Cartography* (CACM 2015). [MSR](https://www.microsoft.com/en-us/research/publication/trains-thought-generating-information-maps/), [CACM PDF](https://ai.stanford.edu/~jure/pubs/cartography-cacm15.pdf)
- Liu 외. *Story Forest.* TKDD 2020 / CIKM 2017. [arXiv 1803.00189](https://arxiv.org/pdf/1803.00189)
- Hu, Moon, Ng. *From Moments to Milestones: Incremental TLS Leveraging LLMs.* ACL 2024. [ACL Anthology](https://aclanthology.org/2024.acl-long.390); 비용 비교 [TimelineReasoner](https://arxiv.org/pdf/2605.12518)
- Wu 외. *Unfolding the Headline (CHRONOS).* NAACL 2025 Findings. [arXiv 2501.00888](https://arxiv.org/abs/2501.00888v1)

**예측·외부 시각**
- Halawi 외. *Approaching Human-Level Forecasting with Language Models.* NeurIPS 2024. [arXiv 2402.18563](https://arxiv.org/pdf/2402.18563.pdf)
- Green, Armstrong. *Structured Analogies for Forecasting.* IJF 2007. [Penn](https://repository.upenn.edu/marketing_papers/166), [Monash](https://bridges.monash.edu/articles/journal_contribution/Structured_Analogies_for_Forecasting/5090170)

**기술 인텔리전스·미래연구**
- Ansoff 약신호 리뷰. [Strathclyde](https://strathprints.strath.ac.uk/81235/); 약신호 텍스트 마이닝 [WISDOM](https://arxiv.org/pdf/2409.15340), [Emerging technologies weak signals](https://arxiv.org/pdf/2205.05449), [Fraunhofer ISI 방법론](https://www.isi.fraunhofer.de/content/dam/isi/dokumente/ccv/observe/Deliverable-1-3_Methodology-Report.pdf)
- Zucker, Darby. 스타 과학자와 창업. [NBER Reporter](https://www.nber.org/reporter/fall-1998/entrepreneurs-star-scientists-and-biotechnology), [PNAS 1996](https://pmc.ncbi.nlm.nih.gov/articles/PMC34126)
- Porter. *Technology foresight: types and methods.* 2010. [Georgia Tech](https://spp.gatech.edu/publications/pub/3325); 세 지평·미래 바퀴 실무 사례 [UK HSE](https://www.gov.uk/government/publications/future-of-energy-three-horizons-and-futures-wheels-health-and-safety-executive/future-of-energy-three-horizons-futures-wheels); 정보연구와 미래연구의 접점 [Kaivo-oja](https://centrumbalticum.org/jari-kaivo-oja-interfaces-between-intelligence-research-and-foresight-research-promoting-fruitful-interfaces)

**정보분석 작법**
- US Government. *A Tradecraft Primer: Structured Analytic Techniques.* 2009. [CIA](https://www.cia.gov/resources/csi/static/955180a45afe3f5013772c313b16face/Tradecraft-Primer-apr09.pdf)
- ODNI. *ICD 203 Analytic Standards.* [FAS 사본](https://irp.fas.org/dni/icd/icd-203.pdf); 확신도 사용 연구노트 [DNI 2024](https://www.dni.gov/files/documents/FOIA/DF-2024-00001-NIU_Research_Short.pdf)

**LLM 보고서 생성**
- Shao 외. *Assisting in Writing Wikipedia-like Articles From Scratch with LLMs (STORM).* 2024. [arXiv 2402.14207](https://arxiv.org/html/2402.14207v2)
- Du 외. *DeepResearch Bench.* 2025. [arXiv 2506.11763](https://arxiv.org/pdf/2506.11763)

**사례(르쿤·AMI Labs) 확인**
- [SiliconANGLE 2026-03-10](https://siliconangle.com/2026/03/10/yann-lecuns-new-startup-ami-labs-raises-1-03b-train-world-models/), [Sifted](https://sifted.eu/articles/yann-lecun-ami-labs-meta-funding-round-nvidia), [Futurum](https://futurumgroup.com/insights/yann-lecuns-ami-raises-1bn-seed-round-is-the-world-model-era-finally-here)
- OpenAlex 저자 소속 필드 [문서](https://docs.openalex.org/api-entities/authors/author-object)


---

## 12. R1 구현 — 주제 요청 보고서 (2026-10-13)

### 12-1. 사용 흐름

1. 리더 메뉴 **동향 보고서 작성**(`/reports`) — 주제, 정보·관점(알고 있는 사실, 궁금한 점, 꼭 다룰 기업·인물), 근거 기간(30·90·180·365일)을 넣고 "보고서 요청". 주제 파일 상세의 "동향 보고서" 버튼은 그 주제 파일의 제목·설명·조건을 넘긴다.
2. 요청은 대기열(`trend_reports`)에 들어가고 상세 화면이 대기 순서·작성 중을 보이며 자동으로 새로 고쳐진다.
3. 호스트 launchd(`com.newsinsight.reports`, 1분마다 `scripts/dev.sh reports`)가 가장 오래된 요청을 집어 Claude CLI(`REPORT_MODEL`, 기본 opus)로 쓴다. 한 실행에 최대 3건, 잠금 파일로 겹치지 않는다.
4. 완료되면 상세 화면에 보고서가 틀(iframe)로 보이고 "새 창으로", HTML·Markdown·Word·PowerPoint 내보내기가 있다. 실패하면 이유와 "다시 시도".

### 12-2. 구성

| 위치 | 내용 |
|---|---|
| `reports/models.py`, 마이그레이션 0040 | `trend_reports`: 주제·설명·기간·주제 파일, 상태(queued·running·ready·failed·archived), 검색 계획, 검증된 본문(JSON), 근거·통계, HTML, 모델·비용·오류 |
| `reports/prompts.py` | 계획 프롬프트·스키마, 작성 프롬프트·스키마(§2의 방법과 작법: 결론 먼저, 양태, 시계열·지형·선례·DX, 핵심 가정, 경쟁 가설, 관찰 지표, ICD 203 가능성 7단계, 배경지식 표시) |
| `reports/evidence.py` | 검색 계획 정리, 근거 수집(키워드·기업·의미·주제 파일), 이슈당 1건·주별 균형, 통계·주체별 타임라인 |
| `reports/render.py` | 인용 검증, 단일 HTML(스크립트 없음, 밝은·어두운 테마, 인쇄), 내보내기 문서 모델 |
| `reports/service.py` | 요청·한도·대기열·작성·실패 처리(45분 넘게 작성 중이면 다시 대기, 2회 뒤 실패) |
| `reports/routes.py` | `/api/public/reports` (리더 키 + 세션): 목록·요청·상세·`/html`·`/export`·다시 시도·보관 |
| `cli.py` | `news-insight reports run [--limit 3] [--model]`, `reports status` |
| 웹 | `/reports`, `/reports/{id}`, `/reports/{id}/view`(CSP·샌드박스로 HTML 제공), `/export/report/{id}`, 메뉴 "동향 보고서 작성", 주제 파일 버튼 |
| 호스트 | `ops/launchd/com.newsinsight.reports.plist.template`, `scripts/install-report-schedule.sh` |

### 12-3. 한도와 안전

- 하루 요청 한도: 사용자당 `REPORT_USER_DAILY`(5, 관리자는 제외), 사이트 전체 `REPORT_SITE_DAILY`(20). 사용자당 대기·작성 중 2건.
- Claude는 도구 없이, 빈 임시 디렉터리에서, 비밀값을 뺀 환경으로 실행된다(다이제스트와 같은 `ClaudeCli`). 입력 데이터의 지시문은 따르지 않도록 프롬프트에 적었다.
- 보고서 HTML은 우리가 이스케이프해 만든 것이고, 모델이 쓴 글은 텍스트로만 들어간다. 그래도 `default-src 'none'` CSP와 스크립트 없는 iframe 샌드박스로 연다. 외부 링크는 새 창.
- 사이트 전체는 Caddy가 `X-Frame-Options: DENY`·`frame-ancestors 'none'`으로 틀(iframe) 안 표시를 막는다. 첫 배포에서 보고서 틀이 "연결을 거부했습니다"로 비었다(새 창은 정상). `/reports/{id}/view` 경로만 같은 출처의 틀을 허용(`SAMEORIGIN`, `frame-ancestors 'self'`)하도록 Caddy에 별도 헤더 블록을 두었다.
- 보고서는 팀 공유(주제 파일과 같음). 보관은 요청자나 관리자만.

### 12-4. 운영

```bash
scripts/install-report-schedule.sh          # 운영 트리에서 한 번: launchd 등록
cd apps/api && uv run --env-file ../../.env news-insight reports status
tail -f ops/logs/reports.log
```
