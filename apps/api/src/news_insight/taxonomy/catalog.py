"""Classification axes (requirements §9): 15 fields × 5 themes, 6 DX businesses, impact, scope.

The field/theme tree follows the v3 catalog. Bumping TAXONOMY_REVISION makes the card
runner regenerate cards so every item is classified against the current tree.
"""

from dataclasses import dataclass

TAXONOMY_REVISION = "2026-10-04.1"


@dataclass(frozen=True)
class Node:
    key: str
    name: str


@dataclass(frozen=True)
class Field(Node):
    themes: tuple[Node, ...]


def _field(key: str, name: str, themes: tuple[tuple[str, str], ...]) -> Field:
    return Field(key, name, tuple(Node(f"{key}__{suffix}", label) for suffix, label in themes))


FIELDS: tuple[Field, ...] = (
    _field(
        "ai_data",
        "AI·데이터",
        (
            ("generative_foundation", "생성형 AI·기반모델"),
            ("ai_agents", "AI 에이전트"),
            ("multimodal", "멀티모달·비전·음성"),
            ("edge_ai", "온디바이스·엣지 AI"),
            ("mlops_data", "MLOps·데이터 플랫폼"),
        ),
    ),
    _field(
        "semiconductor",
        "반도체",
        (
            ("memory_hbm_cxl", "메모리·HBM·CXL"),
            ("foundry_process", "파운드리·미세공정"),
            ("soc_npu", "System LSI·SoC·NPU"),
            ("advanced_packaging", "첨단 패키징·칩렛"),
            ("eda_material_equipment", "EDA·소재·장비"),
        ),
    ),
    _field(
        "mobile_edge",
        "모바일·엣지",
        (
            ("android_mobile_os", "Android·모바일 OS"),
            ("smartphone_compute", "스마트폰·모바일 컴퓨팅"),
            ("edge_computing", "엣지 컴퓨팅"),
            ("wearable_health", "웨어러블·디지털 헬스"),
            ("app_service_ecosystem", "앱·서비스 생태계"),
        ),
    ),
    _field(
        "display_media",
        "디스플레이·미디어",
        (
            ("oled_microled", "OLED·MicroLED"),
            ("display_imaging", "디스플레이 구동·영상처리"),
            ("tv_media_platform", "TV·미디어 플랫폼"),
            ("xr_spatial_display", "XR·공간 디스플레이"),
            ("codec_content", "코덱·콘텐츠 기술"),
        ),
    ),
    _field(
        "network_comms",
        "네트워크·통신",
        (
            ("fiveg_sixg", "5G·6G"),
            ("ran_core", "RAN·코어망"),
            ("short_range_wireless", "Wi-Fi·UWB·Bluetooth"),
            ("satellite_ntn", "위성·NTN"),
            ("network_automation_security", "네트워크 자동화·보안"),
        ),
    ),
    _field(
        "cloud_infra",
        "클라우드·인프라",
        (
            ("public_hybrid_cloud", "퍼블릭·하이브리드 클라우드"),
            ("kubernetes_container", "Kubernetes·컨테이너"),
            ("platform_engineering", "플랫폼 엔지니어링"),
            ("sre_observability", "SRE·관측성"),
            ("finops_green_compute", "FinOps·그린 컴퓨팅"),
        ),
    ),
    _field(
        "software_dev",
        "소프트웨어·개발",
        (
            ("language_compiler", "프로그래밍 언어·컴파일러"),
            ("web_app_framework", "웹·앱 프레임워크"),
            ("api_distributed", "API·분산 시스템"),
            ("cicd_testing", "CI/CD·테스트"),
            ("developer_experience", "개발자 경험·도구"),
        ),
    ),
    _field(
        "open_source",
        "오픈소스·생태계",
        (
            ("project_trends", "프로젝트 트렌드"),
            ("community_health", "메인테이너·커뮤니티 건강성"),
            ("license_governance", "라이선스·거버넌스"),
            ("supply_chain_sbom", "공급망·SBOM"),
            ("enterprise_adoption", "기업 채택·기여"),
        ),
    ),
    _field(
        "security_privacy",
        "보안·프라이버시",
        (
            ("application_security", "애플리케이션 보안"),
            ("cloud_security", "클라우드·인프라 보안"),
            ("device_hardware_security", "디바이스·하드웨어 보안"),
            ("identity_zero_trust", "ID·제로트러스트"),
            ("privacy_cryptography", "프라이버시·암호기술"),
        ),
    ),
    _field(
        "robotics_auto",
        "로보틱스·자율시스템",
        (
            ("humanoid_service_robot", "휴머노이드·서비스 로봇"),
            ("embodied_ai", "Embodied AI"),
            ("autonomous_adas", "자율주행·ADAS"),
            ("drone_unmanned", "드론·무인이동체"),
            ("sensor_control_twin", "센서·제어·디지털 트윈"),
        ),
    ),
    _field(
        "manufacturing_supply",
        "제조·공급망",
        (
            ("smart_factory", "스마트 팩토리"),
            ("industrial_ai", "산업 AI·자동화"),
            ("scm_logistics", "SCM·물류"),
            ("quality_yield", "품질·수율"),
            ("supply_resilience", "공급망 회복탄력성"),
        ),
    ),
    _field(
        "product_market",
        "제품·시장",
        (
            ("consumer_electronics", "소비자 전자"),
            ("b2b_enterprise", "B2B·엔터프라이즈"),
            ("customer_design", "고객경험·디자인"),
            ("competition_partnership", "경쟁·파트너십·M&A"),
            ("pricing_revenue", "가격·수익모델"),
        ),
    ),
    _field(
        "finance_investment",
        "재무·투자",
        (
            ("macro_fx", "거시경제·환율"),
            ("capex_investment", "CAPEX·설비투자"),
            ("cost_economics", "원가·단위경제성"),
            ("valuation_ir", "기업가치·IR"),
            ("financial_risk", "재무·사업 리스크"),
        ),
    ),
    _field(
        "policy_ip_standards",
        "정책·IP·표준",
        (
            ("technology_regulation", "기술 규제"),
            ("ai_governance_ethics", "AI 거버넌스·윤리"),
            ("patent_litigation", "특허·소송·라이선스"),
            ("international_standards", "국제표준"),
            ("export_geopolitics", "수출통제·지정학"),
        ),
    ),
    _field(
        "emerging_science",
        "미래과학·지속가능성",
        (
            ("quantum_technology", "양자기술"),
            ("neuromorphic_photonic", "뉴로모픽·포토닉스"),
            ("advanced_materials", "첨단소재"),
            ("battery_energy", "배터리·에너지"),
            ("carbon_circularity", "탄소·순환경제"),
        ),
    ),
)

BUSINESSES: tuple[Node, ...] = (
    Node("mx", "MX · 모바일·온디바이스 AI"),
    Node("vd", "VD · 디스플레이·영상"),
    Node("da", "DA · 생활가전·홈로봇"),
    Node("networks", "Networks · 5G Adv·6G"),
    Node("health", "Health · 디지털 헬스·의료기기"),
    Node("harman", "Harman · 전장·SDV"),
)
IMPACTS: tuple[Node, ...] = (
    Node("opportunity", "기회"),
    Node("risk", "위험"),
    Node("watch", "관찰"),
)
SCOPES: tuple[Node, ...] = (
    Node("dx", "DX 제품·기술"),
    Node("dx_dependency", "DX 기술 의존성"),
    Node("excluded", "반도체 자산 투자(제외)"),
    Node("irrelevant", "무관"),
)

FIELD_KEYS = frozenset(field.key for field in FIELDS)
THEME_KEYS = frozenset(theme.key for field in FIELDS for theme in field.themes)
BUSINESS_KEYS = frozenset(node.key for node in BUSINESSES)
IMPACT_KEYS = frozenset(node.key for node in IMPACTS)
SCOPE_KEYS = frozenset(node.key for node in SCOPES)
LABELS: dict[str, str] = {
    node.key: node.name
    for node in (*FIELDS, *(t for f in FIELDS for t in f.themes), *BUSINESSES, *IMPACTS, *SCOPES)
}


def prompt_outline() -> str:
    """Compact tree for the card prompt: 'field: theme_suffix(이름), …' per line."""
    lines = []
    for field in FIELDS:
        themes = ", ".join(f"{theme.key.split('__', 1)[1]}({theme.name})" for theme in field.themes)
        lines.append(f"{field.key}({field.name}): {themes}")
    return "\n".join(lines)
