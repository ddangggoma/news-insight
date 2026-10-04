// Generated from apps/api/src/news_insight/taxonomy/catalog.py by
// apps/api/scripts/gen_taxonomy_ts.py — do not edit by hand.
export const TAXONOMY_REVISION = "2026-10-05.1";
export const TAXONOMY_REVISED_ON = "2026-10-05";

export const FIELD_LABEL: Record<string, string> = {
  "ai": "AI 모델·에이전트",
  "semis": "반도체·컴퓨팅 HW",
  "display_av": "디스플레이·영상·오디오",
  "connectivity": "무선·네트워크",
  "platform_sw": "플랫폼·소프트웨어",
  "cloud_data": "클라우드·데이터센터",
  "security": "보안·신뢰",
  "robotics_mobility": "로보틱스·모빌리티",
  "health_tech": "헬스테크",
  "energy": "에너지·지속가능성",
  "manufacturing": "제조 기술",
  "frontier": "미래 기술"
};

export const THEME_LABEL: Record<string, string> = {
  "ai__foundation_models": "기반모델·LLM",
  "ai__multimodal_perception": "멀티모달·비전·음성",
  "ai__ai_agents": "AI 에이전트",
  "ai__on_device_ai": "온디바이스 AI·디바이스 AI 경험",
  "ai__model_efficiency": "경량화·SLM·양자화",
  "ai__ai_coding": "AI 코딩·개발 에이전트",
  "ai__ai_safety_eval": "AI 평가·안전성·해석가능성",
  "semis__ap_soc_npu": "모바일 AP·SoC·NPU",
  "semis__memory_storage": "메모리·스토리지",
  "semis__packaging_chiplet": "첨단 패키징·칩렛",
  "semis__sensor_chips": "이미지센서·MEMS·센서칩",
  "semis__power_rf_semis": "전력·RF 반도체",
  "display_av__display_panel": "디스플레이 패널",
  "display_av__picture_processing": "화질·영상처리",
  "display_av__camera_imaging": "카메라·컴퓨테이셔널 포토",
  "display_av__audio_acoustics": "오디오·음향",
  "display_av__codec_streaming": "코덱·스트리밍·방송 기술",
  "display_av__xr_spatial": "XR·공간컴퓨팅·AI 글래스",
  "connectivity__cellular_5g_6g": "5G-Adv·6G",
  "connectivity__ran_core": "RAN·코어",
  "connectivity__short_range_wireless": "Wi-Fi·UWB·Bluetooth·NFC",
  "connectivity__satellite_ntn": "위성·NTN·D2D",
  "connectivity__smart_home_iot": "스마트홈·IoT 연결",
  "connectivity__network_ops": "네트워크 자동화·운영",
  "platform_sw__device_os": "디바이스 OS·플랫폼",
  "platform_sw__app_ecosystem": "앱·서비스·스토어·결제",
  "platform_sw__developer_tools": "개발 언어·프레임워크·도구",
  "platform_sw__web_cross_platform": "웹·크로스플랫폼",
  "platform_sw__ux_accessibility": "UX·접근성·디자인 시스템",
  "cloud_data__ai_datacenter": "AI 데이터센터·전력·냉각",
  "cloud_data__cloud_platforms": "클라우드·소버린 클라우드",
  "cloud_data__edge_cloud": "엣지 컴퓨팅·MEC",
  "cloud_data__data_ml_platform": "데이터·MLOps 플랫폼",
  "cloud_data__infra_ops": "인프라 운영",
  "security__device_security": "디바이스·HW 보안",
  "security__app_cloud_security": "앱·클라우드 보안",
  "security__identity_auth": "인증·ID",
  "security__privacy_crypto": "프라이버시·암호·PQC",
  "security__ai_security_provenance": "AI 보안·콘텐츠 출처증명",
  "security__software_supply_chain": "SW 공급망·취약점",
  "robotics_mobility__home_service_robot": "홈·서비스 로봇",
  "robotics_mobility__humanoid_embodied": "휴머노이드·Embodied AI",
  "robotics_mobility__autonomous_driving": "자율주행·ADAS",
  "robotics_mobility__sdv_cockpit": "SDV·디지털 콕핏·차량 OS",
  "robotics_mobility__sensing_digital_twin": "센서 퓨전·디지털 트윈",
  "health_tech__biosensing": "디지털 바이오마커·비침습 센싱",
  "health_tech__medical_ai_samd": "AI 의료기기·SaMD",
  "health_tech__remote_care": "원격진료·원격 모니터링",
  "health_tech__health_data_interop": "의료데이터 표준·연동",
  "health_tech__aging_care": "에이징테크·돌봄",
  "energy__battery_charging": "배터리·충전",
  "energy__home_energy": "가정 에너지·HEMS",
  "energy__power_efficiency": "저전력·고효율 설계",
  "energy__circular_materials": "순환·친환경 소재·수리성",
  "manufacturing__smart_factory": "스마트 팩토리·산업 AI",
  "manufacturing__quality_inspection": "품질·검사 AI",
  "manufacturing__factory_robotics": "제조 로봇·협동로봇",
  "manufacturing__logistics_automation": "물류·창고 자동화",
  "frontier__quantum": "양자 컴퓨팅·통신·센싱",
  "frontier__neuromorphic_photonic": "뉴로모픽·광컴퓨팅",
  "frontier__advanced_materials": "신소재",
  "frontier__neurotech_bci": "뉴로테크·BCI"
};

export const SIGNAL_LABEL: Record<string, string> = {
  "research": "연구·논문",
  "launch": "제품·기능 출시",
  "standard": "표준·인증",
  "regulation": "정책·규제",
  "market": "시장·경쟁·제휴",
  "finance": "투자·실적",
  "ecosystem": "오픈소스·생태계",
  "security_event": "취약점·보안 사고",
  "supply": "공급망·생산",
  "ip": "특허·소송"
};

export const IMPACT_LABEL: Record<string, string> = {
  "opportunity": "기회",
  "risk": "위험",
  "watch": "관찰"
};

export const SCOPE_LABEL: Record<string, string> = {
  "dx": "DX 제품·기술",
  "dx_dependency": "DX 기술 의존성",
  "excluded": "반도체 자산 투자(제외)",
  "irrelevant": "무관"
};
