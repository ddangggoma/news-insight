"""Classification axes, taxonomy v2 (plan 09): technology fields → themes (→ technologies in
the registry), signal type, impact and scope. There is no DX business axis.

Bumping TAXONOMY_REVISION queues every card for classification-only reclassification
(checklist CLS-2); card text is not regenerated.
"""

from dataclasses import dataclass

TAXONOMY_TREE = "2026-10-05"  # field/theme keys; revisions of one tree share them
TAXONOMY_REVISION = f"{TAXONOMY_TREE}.1"
PROVISIONAL_REVISION = f"{TAXONOMY_TREE}.0"  # deterministic mapping from the previous tree
# first day classified with this tree; the radar marks comparisons that cross it
TAXONOMY_REVISED_ON = "2026-10-05"


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
        "ai",
        "AI 모델·에이전트",
        (
            ("foundation_models", "기반모델·LLM"),
            ("multimodal_perception", "멀티모달·비전·음성"),
            ("ai_agents", "AI 에이전트"),
            ("on_device_ai", "온디바이스 AI·디바이스 AI 경험"),
            ("model_efficiency", "경량화·SLM·양자화"),
            ("ai_coding", "AI 코딩·개발 에이전트"),
            ("ai_safety_eval", "AI 평가·안전성·해석가능성"),
        ),
    ),
    _field(
        "semis",
        "반도체·컴퓨팅 HW",
        (
            ("ap_soc_npu", "모바일 AP·SoC·NPU"),
            ("memory_storage", "메모리·스토리지"),
            ("packaging_chiplet", "첨단 패키징·칩렛"),
            ("sensor_chips", "이미지센서·MEMS·센서칩"),
            ("power_rf_semis", "전력·RF 반도체"),
        ),
    ),
    _field(
        "display_av",
        "디스플레이·영상·오디오",
        (
            ("display_panel", "디스플레이 패널"),
            ("picture_processing", "화질·영상처리"),
            ("camera_imaging", "카메라·컴퓨테이셔널 포토"),
            ("audio_acoustics", "오디오·음향"),
            ("codec_streaming", "코덱·스트리밍·방송 기술"),
            ("xr_spatial", "XR·공간컴퓨팅·AI 글래스"),
        ),
    ),
    _field(
        "connectivity",
        "무선·네트워크",
        (
            ("cellular_5g_6g", "5G-Adv·6G"),
            ("ran_core", "RAN·코어"),
            ("short_range_wireless", "Wi-Fi·UWB·Bluetooth·NFC"),
            ("satellite_ntn", "위성·NTN·D2D"),
            ("smart_home_iot", "스마트홈·IoT 연결"),
            ("network_ops", "네트워크 자동화·운영"),
        ),
    ),
    _field(
        "platform_sw",
        "플랫폼·소프트웨어",
        (
            ("device_os", "디바이스 OS·플랫폼"),
            ("app_ecosystem", "앱·서비스·스토어·결제"),
            ("developer_tools", "개발 언어·프레임워크·도구"),
            ("web_cross_platform", "웹·크로스플랫폼"),
            ("ux_accessibility", "UX·접근성·디자인 시스템"),
        ),
    ),
    _field(
        "cloud_data",
        "클라우드·데이터센터",
        (
            ("ai_datacenter", "AI 데이터센터·전력·냉각"),
            ("cloud_platforms", "클라우드·소버린 클라우드"),
            ("edge_cloud", "엣지 컴퓨팅·MEC"),
            ("data_ml_platform", "데이터·MLOps 플랫폼"),
            ("infra_ops", "인프라 운영"),
        ),
    ),
    _field(
        "security",
        "보안·신뢰",
        (
            ("device_security", "디바이스·HW 보안"),
            ("app_cloud_security", "앱·클라우드 보안"),
            ("identity_auth", "인증·ID"),
            ("privacy_crypto", "프라이버시·암호·PQC"),
            ("ai_security_provenance", "AI 보안·콘텐츠 출처증명"),
            ("software_supply_chain", "SW 공급망·취약점"),
        ),
    ),
    _field(
        "robotics_mobility",
        "로보틱스·모빌리티",
        (
            ("home_service_robot", "홈·서비스 로봇"),
            ("humanoid_embodied", "휴머노이드·Embodied AI"),
            ("autonomous_driving", "자율주행·ADAS"),
            ("sdv_cockpit", "SDV·디지털 콕핏·차량 OS"),
            ("sensing_digital_twin", "센서 퓨전·디지털 트윈"),
        ),
    ),
    _field(
        "health_tech",
        "헬스테크",
        (
            ("biosensing", "디지털 바이오마커·비침습 센싱"),
            ("medical_ai_samd", "AI 의료기기·SaMD"),
            ("remote_care", "원격진료·원격 모니터링"),
            ("health_data_interop", "의료데이터 표준·연동"),
            ("aging_care", "에이징테크·돌봄"),
        ),
    ),
    _field(
        "energy",
        "에너지·지속가능성",
        (
            ("battery_charging", "배터리·충전"),
            ("home_energy", "가정 에너지·HEMS"),
            ("power_efficiency", "저전력·고효율 설계"),
            ("circular_materials", "순환·친환경 소재·수리성"),
        ),
    ),
    _field(
        "manufacturing",
        "제조 기술",
        (
            ("smart_factory", "스마트 팩토리·산업 AI"),
            ("quality_inspection", "품질·검사 AI"),
            ("factory_robotics", "제조 로봇·협동로봇"),
            ("logistics_automation", "물류·창고 자동화"),
        ),
    ),
    _field(
        "frontier",
        "미래 기술",
        (
            ("quantum", "양자 컴퓨팅·통신·센싱"),
            ("neuromorphic_photonic", "뉴로모픽·광컴퓨팅"),
            ("advanced_materials", "신소재"),
            ("neurotech_bci", "뉴로테크·BCI"),
        ),
    ),
)

# What kind of news an item is, independent of its technology (plan 09 §3-2).
SIGNAL_TYPES: tuple[Node, ...] = (
    Node("research", "연구·논문"),
    Node("launch", "제품·기능 출시"),
    Node("standard", "표준·인증"),
    Node("regulation", "정책·규제"),
    Node("market", "시장·경쟁·제휴"),
    Node("finance", "투자·실적"),
    Node("ecosystem", "오픈소스·생태계"),
    Node("security_event", "취약점·보안 사고"),
    Node("supply", "공급망·생산"),
    Node("ip", "특허·소송"),
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

# the wording the classification prompt has used for these nodes (seeded as node definitions,
# plan 15-2), and the lead line of each list scheme
DEFINITIONS: dict[str, str] = {
    "research": "연구·논문·벤치마크",
    "launch": "제품·기능 출시·리뷰",
    "standard": "표준·인증",
    "regulation": "정책·규제·준수",
    "market": "시장·경쟁·제휴·M&A",
    "finance": "투자·실적·CAPEX",
    "ecosystem": "오픈소스·개발자 생태계",
    "security_event": "취약점·보안 사고",
    "supply": "공급망·생산",
    "ip": "특허·소송·라이선스",
    "dx": "완제품·디바이스 제품·기술 직접",
    "dx_dependency": "완제품 성능·원가에 직결되는 부품·기술 의존성",
    "excluded": "메모리·파운드리 증설 같은 반도체 자산 투자 자체",
    "irrelevant": "기술과 무관: 정치·연예·일반 사회·게임 운영·금융 일반·개인 잡담 등",
}
SCHEME_LEADS: dict[str, str] = {
    "signal_type": "어떤 종류의 소식인지 하나",
    "impact": "DX(완제품·디바이스) 관점",
    "scope": "범위 하나",
}

FIELD_KEYS = frozenset(field.key for field in FIELDS)
THEME_KEYS = frozenset(theme.key for field in FIELDS for theme in field.themes)
SIGNAL_TYPE_KEYS = frozenset(node.key for node in SIGNAL_TYPES)
IMPACT_KEYS = frozenset(node.key for node in IMPACTS)
SCOPE_KEYS = frozenset(node.key for node in SCOPES)
LABELS: dict[str, str] = {
    node.key: node.name
    for node in (*FIELDS, *(t for f in FIELDS for t in f.themes), *SIGNAL_TYPES, *IMPACTS, *SCOPES)
}


def prompt_outline() -> str:
    """Compact tree for the card prompt: 'field: theme_suffix(이름), …' per line."""
    lines = []
    for field in FIELDS:
        themes = ", ".join(f"{theme.key.split('__', 1)[1]}({theme.name})" for theme in field.themes)
        lines.append(f"{field.key}({field.name}): {themes}")
    return "\n".join(lines)
