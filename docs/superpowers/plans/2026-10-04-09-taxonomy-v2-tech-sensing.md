# 테마 v2 재검토 — 사업 태그 제거, 기술 센싱 중심 분류

> **요청 (2026-10-04):** DX 부문 분류(MX·VD·NW·DA)는 태그 하나로만 관리합니다. 기술·테마는 효율적으로 센싱할 수 있게 확장안을 다시 검토합니다.
> **결정 (2026-10-04, 후속):** 사업 태그는 **완전히 삭제**하고 분류에서 고려하지 않습니다. 정책·시장·재무·생태계 분야는 신호 유형으로 옮깁니다.
> **대체 범위:** [2026-10-04-08 계획](2026-10-04-08-inspection-and-taxonomy-v2.md)의 §3(테마 v2 확정안)을 이 문서로 대체합니다. 점검표 항목(§2)과 실행 순서는 그대로입니다.
> **근거 데이터:** 운영 DB, 최근 90일, DX 관련(`dx`·`dx_dependency`) 카드 23,933건.

## 1. 지금 체계의 문제 (실데이터)

### 1-1. 사업부를 닮은 분야가 기술 축에 섞여 있다

| 분야 (현재) | 사실상 대응하는 사업부 | 증상 |
|---|---|---|
| 모바일·엣지 | MX | "갤럭시 탭 언박싱", "아너 Magic9 유럽 출시"가 `smartphone_compute` 테마로 들어감. 기술 신호가 아니라 제품 소식 |
| 디스플레이·미디어 | VD | `tv_media_platform`은 기술이 아니라 사업 영역 |
| 네트워크·통신 | NW | 분야 이름 자체가 사업부 |
| (확장안) 헬스·메드테크 | Health | 사업 태그 `health`와 같은 정보를 두 번 저장 |
| 웨어러블·디지털 헬스 테마 | MX·Health | "NFC 기반 시각장애인 접근성 솔루션"이 여기로 감. 실제 기술(NFC·접근성)은 사라짐 |

사업 태그와 분야가 같은 것을 가리키면 두 가지가 나빠집니다.
1. 레이더의 분야×사업부 표가 대각선에만 몰립니다.
2. "MX에 영향을 주는 **다른 분야** 기술"(예: 배터리, PQC, 위성 D2D)이 잘 보이지 않습니다.

### 1-2. 기술이 아닌 분야가 기술 신호를 가린다

| 비기술 분야 | 카드 | 비중 |
|---|---:|---:|
| 정책·IP·표준 | 1,894 | 7.9% |
| 제품·시장 | 1,245 | 5.2% |
| 오픈소스·생태계 | 770 | 3.2% |
| 재무·투자 | 187 | 0.8% |
| **합계** | **4,096** | **17.1%** |

카드당 분야는 하나라서, 이 17%는 기술 집계에서 빠집니다. 예를 들어 "EU 스마트폰 수리성 규제"는 정책으로만 잡히고 배터리·순환 소재 기술 신호에는 0으로 남습니다. "스마트 수면 케어 기기"는 '소비자 전자'로 가서 바이오센싱 신호를 놓칩니다.

### 1-3. 사업 태그 현황 (삭제 대상)

| 태그 | MX | DA | Harman | NW | Health | VD | 태그 없음 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 카드 | 7,566 | 2,866 | 2,696 | 1,755 | 1,691 | 1,068 | 8,699 (36%) |

## 2. 설계 원칙

1. **축을 네 개로 분리합니다.** 각 축은 한 가지만 답합니다. 사업 태그 축은 두지 않습니다.

| 축 | 질문 | 값 | 카드당 |
|---|---|---|---|
| **기술** (분야 → 테마 → 기술) | 무슨 기술 이야기인가 | 12분야 · 62테마 · 기술 약 350개 | 테마 0~2, 기술 1~4 |
| **신호 유형** | 어떤 종류의 소식인가 | 10개 (§3-2) | 1 |
| 영향 | 기회·위험·관찰 | 3 (현행) | 0~1 |
| 범위 | DX 관련 여부 | 4 (현행) | 1 |

2. **분야·테마 이름에 제품군이나 사업부를 쓰지 않습니다.** "TV·미디어 플랫폼", "스마트폰·모바일 컴퓨팅", "소비자 전자", "웨어러블·디지털 헬스" 같은 이름은 없앱니다. 제품 소식은 **신호 유형 = 출시** + 그 제품의 **기술 테마**로 표현합니다.
3. **정책·시장·재무·생태계는 신호 유형으로 옮깁니다.** 모든 카드가 기술 테마를 가질 수 있습니다. 그래서 규제나 시장 기사도 해당 기술의 보도량에 잡힙니다(위 17% 회수).
4. **3단계 '기술'은 통제 어휘로 둡니다.**
   - 기술 키 + 별칭 + 소속 테마 + 상태(활성·감시)를 DB 테이블로 관리합니다(점검표 KW-1을 확장).
   - 카드 키워드를 저장할 때 기술 키로 정규화합니다. 레이더의 '기술' 단계가 이 키를 씁니다.
   - 어디에도 맞지 않는 키워드는 후보 대기열로 보냅니다(CLS-1).
5. **사업 태그는 없습니다.** DX와의 관련은 범위 축(`dx`·`dx_dependency`)과 영향(기회·위험·관찰)만으로 판단합니다. 사업부 관점이 필요한 곳(전략 보고서·페르소나)은 기사 내용으로 LLM이 직접 판단하고, 분류 데이터로 저장하지 않습니다.

## 3. 새 체계

### 3-1. 기술 분야·테마 (12분야, 62테마)

| 분야 | 테마 (키 · 이름) |
|---|---|
| **ai** AI 모델·에이전트 | `foundation_models` 기반모델·LLM · `multimodal_perception` 멀티모달·비전·음성 · `ai_agents` AI 에이전트 · `on_device_ai` 온디바이스 AI·디바이스 AI 경험 · `model_efficiency` 경량화·SLM·양자화 · `ai_coding` AI 코딩·개발 에이전트 · `ai_safety_eval` AI 평가·안전성·해석가능성 |
| **semis** 반도체·컴퓨팅 HW | `ap_soc_npu` 모바일 AP·SoC·NPU · `memory_storage` 메모리·스토리지(LPDDR·HBM·CXL·UFS) · `packaging_chiplet` 첨단 패키징·칩렛 · `sensor_chips` 이미지센서·MEMS·센서칩 · `power_rf_semis` 전력·RF 반도체(GaN·SiC·RF FE) |
| **display_av** 디스플레이·영상·오디오 | `display_panel` 디스플레이 패널(OLED·MicroLED·Micro RGB·QD) · `picture_processing` 화질·영상처리(AI 업스케일·HDR) · `camera_imaging` 카메라·컴퓨테이셔널 포토 · `audio_acoustics` 오디오·음향 · `codec_streaming` 코덱·스트리밍·방송 기술 · `xr_spatial` XR·공간컴퓨팅·AI 글래스 |
| **connectivity** 무선·네트워크 | `cellular_5g_6g` 5G-Adv·6G · `ran_core` RAN·코어(Open RAN·vRAN·AI-RAN) · `short_range_wireless` Wi-Fi·UWB·Bluetooth·NFC · `satellite_ntn` 위성·NTN·D2D · `smart_home_iot` 스마트홈·IoT 연결(Matter·Thread·홈 허브) · `network_ops` 네트워크 자동화·운영 |
| **platform_sw** 플랫폼·소프트웨어 | `device_os` 디바이스 OS·플랫폼(Android·Tizen·One UI) · `app_ecosystem` 앱·서비스·스토어·결제 · `developer_tools` 개발 언어·프레임워크·도구 · `web_cross_platform` 웹·크로스플랫폼(WebGPU·Flutter) · `ux_accessibility` UX·접근성·디자인 시스템 |
| **cloud_data** 클라우드·데이터센터 | `ai_datacenter` AI 데이터센터·전력·냉각·인터커넥트 · `cloud_platforms` 클라우드·소버린 클라우드 · `edge_cloud` 엣지 컴퓨팅·MEC · `data_ml_platform` 데이터·MLOps 플랫폼 · `infra_ops` 인프라 운영(K8s·SRE·FinOps) |
| **security** 보안·신뢰 | `device_security` 디바이스·HW 보안(TEE·보안칩) · `app_cloud_security` 앱·클라우드 보안 · `identity_auth` 인증·ID(패스키·제로트러스트) · `privacy_crypto` 프라이버시·암호·PQC · `ai_security_provenance` AI 보안·출처증명(C2PA·딥페이크) · `software_supply_chain` SW 공급망·취약점(SBOM·CVE) |
| **robotics_mobility** 로보틱스·모빌리티 | `home_service_robot` 홈·서비스 로봇 · `humanoid_embodied` 휴머노이드·Embodied AI·월드모델 · `autonomous_driving` 자율주행·ADAS · `sdv_cockpit` SDV·디지털 콕핏·차량 OS · `sensing_digital_twin` 센서 퓨전·디지털 트윈 |
| **health_tech** 헬스테크 | `biosensing` 디지털 바이오마커·비침습 센싱 · `medical_ai_samd` AI 의료기기·SaMD · `remote_care` 원격진료·원격 모니터링 · `health_data_interop` 의료데이터 표준·연동 · `aging_care` 에이징테크·돌봄 |
| **energy** 에너지·지속가능성 | `battery_charging` 배터리·충전(전고체·고속·무선충전) · `home_energy` 가정 에너지(HEMS·히트펌프·ESS) · `power_efficiency` 저전력·고효율 설계 · `circular_materials` 순환·친환경 소재·수리성 |
| **manufacturing** 제조 기술 | `smart_factory` 스마트 팩토리·산업 AI · `quality_inspection` 품질·검사 AI · `factory_robotics` 제조 로봇·협동로봇 · `logistics_automation` 물류·창고 자동화 |
| **frontier** 미래 기술 | `quantum` 양자 컴퓨팅·통신·센싱 · `neuromorphic_photonic` 뉴로모픽·광컴퓨팅 · `advanced_materials` 신소재(2D·메타물질) · `neurotech_bci` 뉴로테크·BCI |

**확장안 결정과의 관계:**
- 헬스 5개, 분야당 4~7개 규칙은 그대로 유지합니다.
- 확장안의 13개 추가 테마는 모두 담깁니다. 다만 두 개는 형태가 바뀝니다.
  - **제품 규제 준수(CRA·DPP·수리권):** 테마가 아니라 **신호 유형 = 규제**입니다. 기술 쪽은 `circular_materials`·`device_security` 등에 잡히고, CRA·DPP는 규제 항목(§3-3)으로 추적합니다.
  - **소버린 AI:** 별도 테마 대신 `cloud_platforms`의 기술 항목으로 둡니다. 정책 측면은 신호 유형이 맡습니다.
- 그 결과 테마 수는 88개 안에서 **62개**로 줄지만 모두 기술 테마입니다. 테마가 많을수록 카드당 2개 한도에서 신호가 쪼개지므로, 적고 겹치지 않는 편이 센싱에 유리합니다.

**빠지는 현행 테마와 행선지:**

| 현행 테마 | 행선지 |
|---|---|
| `smartphone_compute`, `consumer_electronics`, `tv_media_platform` | 신호 유형 = 출시 + 해당 기술 테마 |
| `wearable_health` | `biosensing` / 출시 |
| `competition_partnership`, `pricing_revenue`, `b2b_enterprise`, `customer_design` | 신호 유형 = 시장 |
| `macro_fx`, `capex_investment`, `cost_economics`, `valuation_ir`, `financial_risk` | 신호 유형 = 재무 |
| `technology_regulation`, `ai_governance_ethics`, `export_geopolitics` | 신호 유형 = 규제 |
| `international_standards` | 신호 유형 = 표준 |
| `patent_litigation` | 신호 유형 = 특허·IP |
| `project_trends`, `community_health`, `license_governance`, `enterprise_adoption` | 신호 유형 = 생태계 |
| `supply_chain_sbom` | `software_supply_chain` |
| `foundry_process`, `eda_material_equipment` | `ap_soc_npu`·`memory_storage`의 기술 항목 (반도체 자산 투자는 범위 `excluded` 유지) |
| `supply_resilience`, `scm_logistics` | 신호 유형 = 공급망 / `logistics_automation` |
| `drone_unmanned` | `autonomous_driving`의 기술 항목 |

### 3-2. 신호 유형 (카드당 1개)

| 키 | 이름 | 흡수하는 현행 분야·테마 |
|---|---|---|
| `research` | 연구·논문·벤치마크 | — |
| `launch` | 제품·기능 출시·리뷰 | 제품·시장 일부, 모바일·디스플레이 제품 소식 |
| `standard` | 표준·인증·규격 | 국제표준 |
| `regulation` | 정책·규제·준수 | 기술 규제, AI 거버넌스, 수출통제, (확장안) 제품 규제 준수 |
| `market` | 시장·경쟁·제휴·M&A | 제품·시장 |
| `finance` | 투자·실적·CAPEX | 재무·투자 |
| `ecosystem` | 오픈소스·개발자 생태계 | 오픈소스·생태계 |
| `security_event` | 취약점·보안 사고 | (보안 분야에서 사건성 기사 분리) |
| `supply` | 공급망·생산 | 공급망 회복탄력성, SCM |
| `ip` | 특허·소송·라이선스 | 특허·소송 |

레이더는 신호 유형으로 "연구가 먼저 오르는 기술", "규제 기한 전 보도 증가", "출시 쏠림"을 분리해 봅니다. 수집 트랙(뉴스·논문·OSS·커뮤니티)은 출처 기준이고 신호 유형은 내용 기준이라 서로 보완합니다.

### 3-3. 3단계 '기술' 레지스트리

테마마다 시드 기술 4~8개, 전체 약 350개로 시작합니다. 테이블 `technologies(key, label, theme_key, kind, status, aliases[])`를 둡니다.
- `kind`: technology · standard · regulation · product_family
- `status`: active · watch

| 테마 | 시드 기술 예시 |
|---|---|
| `on_device_ai` | 온디바이스 LLM, NPU 추론 런타임(LiteRT·ONNX Runtime·ExecuTorch), 실시간 통역, 카메라 AI, AI 컴패니언(감시) |
| `model_efficiency` | 양자화, 지식 증류, SLM, 투기적 디코딩, MoE |
| `humanoid_embodied` | VLA 모델, 월드모델(감시), 피지컬 AI(감시), 원격조작 데이터 |
| `display_panel` | QD-OLED, MicroLED, Micro RGB, 폴더블·롤러블 패널, OLEDoS |
| `xr_spatial` | AI 글래스(감시), Android XR, 공간 비디오, 마이크로 디스플레이 |
| `cellular_5g_6g` | 5G-Advanced, 6G(감시), RedCap, 앰비언트 IoT(감시) |
| `short_range_wireless` | Wi-Fi 7, Wi-Fi 8(감시), UWB, Bluetooth LE Audio, NFC |
| `satellite_ntn` | NTN, 위성 D2D(감시), Starlink Direct to Cell |
| `smart_home_iot` | Matter, Thread, SmartThings, 홈 허브, Matter 카메라 |
| `ai_datacenter` | 액체·침지 냉각, CPO(감시), 실리콘 포토닉스, SMR 전력, 랙 전력 밀도 |
| `cloud_platforms` | 소버린 클라우드, 국가 AI 기반모델, 멀티클라우드 |
| `privacy_crypto` | PQC(감시)·ML-KEM·ML-DSA, 연합학습, 차등 프라이버시, 기밀 컴퓨팅(감시) |
| `ai_security_provenance` | C2PA, 생성 워터마킹, 딥페이크 탐지, 프롬프트 인젝션 |
| `sdv_cockpit` | 존 아키텍처, 차량 HPC, AAOS, 차량 이더넷, OTA |
| `biosensing` | 커프리스 혈압, 비침습 혈당, PPG·ECG, 수면무호흡 감지 |
| `circular_materials` | 재생 소재, 수리성 설계, 배터리 여권 |
| 규제 항목 (kind=regulation) | EU CRA, EU DPP·ESPR, EU AI Act, 한국 AI 기본법, NIST IR 8547 |

**효율 장치:**
- **정규화:** 저장할 때 키워드를 기술 키로 바꿉니다(별칭 테이블). 레이더 기술 단계는 정규식 대신 GIN 인덱스로 조회합니다.
- **후보 대기열:** 30일에 10건 이상인데 어디에도 맞지 않는 키워드는 콘솔에 올려 "기술로 추가 / 별칭으로 / 무시" 중 하나로 처리합니다.
- **승격·강등 규칙(월 1회 자동 제안):**
  - 감시 기술은 분기 30건이 넘고 2개 기간 연속 상승하면 활성으로 올립니다.
  - 기술이 테마 안에서 lift 3 이상을 유지하고 분기 100건을 넘으면 테마 후보가 됩니다.
  - 테마가 분기 10건 미만이면 병합 후보가 됩니다.
- **테마 프롬프트는 짧게:** 카드 LLM은 테마(62개)와 신호 유형(10개)만 고릅니다. 기술은 키워드에서 결정적으로 정규화하므로 프롬프트가 커지지 않습니다.

### 3-4. 사업 태그 제거와 영향 범위

`item_cards.businesses`, `BUSINESSES`·`BUSINESS_KEYS`, 사업부 필터를 모두 없앱니다. 지금 쓰이는 곳과 대체 방식은 다음과 같습니다(API 20개, 웹 18개 파일).

| 쓰이는 곳 | 대체 |
|---|---|
| 카드 생성·분류 프롬프트와 출력(`businesses`) | 삭제. 프롬프트가 짧아져 카드당 토큰이 줄어듦 |
| 공개 API 필터·패싯·인사이트(`business=`), 탐색 패싯 | 삭제. 신호 유형 필터·패싯으로 교체 |
| 레이더 사업부 필터 칩·토픽 패널의 사업부 분해 (#18) | 삭제. 신호 유형 칩·분해로 교체 (레이더 세션) |
| 브리핑 화면 "시장 영향도"(사업부별 기회·위험) | **분야별** 기회·위험·관찰 막대로 교체 |
| 다이제스트 번들의 `businesses` | 삭제 (`signal_type`으로 교체) |
| 전략 보고서 "DX 사업부별 주장"(`report.businesses`, `BUSINESS_KEYS` 검증) | **기술 분야별 주장**(`report.fields`, 분야 키로 검증)으로 교체. 1·3·5년 로드맵, 기회·위험은 유지 |
| 30개 페르소나 중 사업부장 6명 | 역할(페르소나)이므로 **유지**. 기사 내용으로 판단하고 태그는 쓰지 않음 |
| 콘솔 카드·이슈 묶음 필터, 분류 배지 | 사업부 제거, 신호 유형 추가 |
| 지난 카드 데이터 | 컬럼 삭제는 재분류가 끝난 뒤 별도 마이그레이션으로 (롤백 여지) |

## 4. 시스템 반영 (08 계획 B 단계에 통합)

| 순서 | 작업 | 바뀌는 것 |
|---|---|---|
| B1 | 분류 전용 재분류 경로 | `classification_revision`, 분류 전용 프롬프트에 신호 유형 출력 추가 |
| B3' | 기술 레지스트리 (KW-1 확장) | `technologies`·`technology_aliases` 테이블, `item_cards.technology_keys`(GIN), 콘솔 편집·후보 대기열 화면, 확장안 별칭·감시 목록을 시드로 |
| B4' | 체계 v2 적용 | `catalog.py`(12분야·62테마, `SIGNAL_TYPES`, `BUSINESSES` 삭제), `item_cards.signal_type` 컬럼, 사업 태그 제거(§3-4 표 전부), 전략 보고서 분야별 섹션, 테스트(분야 12, 분야당 4~7), 웹 `taxonomy.ts`, 공개 API 필터 `signal_type`, 레이더에 개정 시점 표시 → **전체 즉시 재분류** |
| B5 | 소스 보강 | 08 계획 B5 그대로 |
| 레이더 세션 | 화면 반영 | 기술 단계를 `technology_keys`로, 사업부 필터 칩을 신호 유형 칩으로 교체 |

**검증 기준:**
- 재분류 뒤 기술 테마가 없는 DX 관련 카드가 5% 미만이어야 합니다(지금은 17%가 비기술 분야).
- 무작위 200건을 표본 검토해 테마 정확도 85% 이상이어야 합니다(관련성 검토 화면 재사용).
- 분야×신호 유형 표로 "연구가 앞서는 분야", "규제가 몰리는 분야"를 구분할 수 있어야 합니다.

## 5. 결정 (2026-10-04)

| 질문 | 결정 |
|---|---|
| 사업 태그 | **삭제.** 분류에서 사업부를 고려하지 않음 (§3-4) |
| 비기술 분야 | **신호 유형으로 이동** (§3-2) |
| 헬스 테마 수·분야당 규칙 | 08 결정 유지: 헬스 5개, 분야당 4~7개 |
| 재분류 범위 | 08 결정 유지: 전체 즉시 (분류 전용 경로로) |
