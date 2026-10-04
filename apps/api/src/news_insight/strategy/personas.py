"""30 active personas (requirements §7): 4 executives, 6 DX business heads, 20 domain leads."""

from dataclasses import dataclass

PERSONA_REVISION = "2026-10-04.1"


@dataclass(frozen=True)
class Persona:
    key: str
    name: str
    group: str  # executive | business | domain
    focus: str


PERSONAS: tuple[Persona, ...] = (
    Persona("ceo", "CEO", "executive", "전사 포트폴리오·경쟁 구도·M&A·글로벌 리스크"),
    Persona("cto", "CTO", "executive", "핵심 기술 로드맵·플랫폼 전환·R&D 우선순위"),
    Persona(
        "cfo", "CFO", "executive", "원가·가격·수익성·환율 등 재무 영향 (반도체 자산 투자 제외)"
    ),
    Persona("dx_head", "DX 부문장", "executive", "DX 사업부 간 시너지·고객 경험·생태계 전략"),
    Persona("mx_head", "MX 사업부장", "business", "스마트폰·태블릿·웨어러블·온디바이스 AI"),
    Persona("vd_head", "VD 사업부장", "business", "TV·모니터·디스플레이 기술·영상 플랫폼"),
    Persona("da_head", "DA 사업부장", "business", "생활가전·스마트홈·홈로봇"),
    Persona("networks_head", "네트워크 사업부장", "business", "5G Advanced·6G·RAN·위성 통신"),
    Persona("health_head", "의료기기 사업부장", "business", "디지털 헬스·의료 영상·규제"),
    Persona("harman_head", "전장(Harman) 사업부장", "business", "SDV·차량 인포테인먼트·ADAS"),
    Persona("ai_ondevice", "온디바이스 AI 리드", "domain", "NPU·경량 모델·양자화·로컬 추론"),
    Persona(
        "genai_services", "생성형 AI 서비스 리드", "domain", "어시스턴트·에이전트·멀티모달 서비스"
    ),
    Persona("display_tech", "디스플레이 기술 리드", "domain", "OLED·MicroLED·폴더블·광학"),
    Persona("camera_imaging", "카메라·이미징 리드", "domain", "이미지 센서·계산 사진·영상 처리"),
    Persona("battery_power", "배터리·전력 리드", "domain", "셀 화학·충전·전력 효율"),
    Persona("connectivity", "근거리 연결 리드", "domain", "Wi-Fi·Bluetooth·UWB·Thread"),
    Persona("sixg_research", "6G 연구 리드", "domain", "6G 표준·RIS·NTN·주파수"),
    Persona("smarthome_iot", "스마트홈·IoT 리드", "domain", "Matter·SmartThings·기기 연동"),
    Persona("robotics", "로보틱스 리드", "domain", "홈로봇·휴머노이드·Embodied AI"),
    Persona("xr_spatial", "XR·공간 컴퓨팅 리드", "domain", "헤드셋·스마트 안경·공간 UI"),
    Persona("wearable_health", "웨어러블 헬스 리드", "domain", "생체 센서·수면·심혈관 모니터링"),
    Persona("medical_regulatory", "의료 규제 리드", "domain", "FDA·MFDS 인허가·임상 근거"),
    Persona("sdv_software", "SDV 소프트웨어 리드", "domain", "차량 OS·OTA·전장 아키텍처"),
    Persona("adas_autonomy", "ADAS·자율주행 리드", "domain", "센서 퓨전·LiDAR·자율주행 규제"),
    Persona(
        "security_privacy", "보안·프라이버시 리드", "domain", "디바이스 보안·취약점·개인정보 규제"
    ),
    Persona("platform_os", "플랫폼·OS 리드", "domain", "Android·One UI·Tizen·앱 생태계"),
    Persona("design_ux", "디자인·UX 리드", "domain", "폼팩터·인터랙션·접근성"),
    Persona(
        "supply_chain", "공급망 리드", "domain", "부품 조달·지정학·물류 (반도체 증설 자체 제외)"
    ),
    Persona("ip_standards", "특허·표준 리드", "domain", "특허 분쟁·표준 필수 특허·국제 표준"),
    Persona("market_competition", "시장·경쟁 분석 리드", "domain", "경쟁사 출시·점유율·가격 전략"),
)

PERSONA_KEYS = frozenset(persona.key for persona in PERSONAS)
