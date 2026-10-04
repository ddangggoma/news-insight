"""Provisional move of existing cards from the previous tree (15 fields × 5 themes, business
tags) to taxonomy v2, so readers never see an empty radar while the LLM reclassifies.

Rules (plan 09 §3-1 table "빠지는 현행 테마와 행선지"):
- each old theme maps to one v2 theme; policy, market, finance and open-source themes map
  to a signal type instead of a theme;
- cards left without a theme take up to two themes from their keywords' registry entries;
- the result is stamped PROVISIONAL_REVISION, which the classification lane still treats as
  stale, so the LLM replaces it newest-first.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from news_insight.cards.models import CardStatus, ItemCard
from news_insight.taxonomy.catalog import PROVISIONAL_REVISION, TAXONOMY_TREE, THEME_KEYS
from news_insight.technologies.models import Technology

THEME_MAP: dict[str, str | None] = {
    "ai_data__generative_foundation": "ai__foundation_models",
    "ai_data__ai_agents": "ai__ai_agents",
    "ai_data__multimodal": "ai__multimodal_perception",
    "ai_data__edge_ai": "ai__on_device_ai",
    "ai_data__mlops_data": "cloud_data__data_ml_platform",
    "semiconductor__memory_hbm_cxl": "semis__memory_storage",
    "semiconductor__foundry_process": "semis__ap_soc_npu",
    "semiconductor__soc_npu": "semis__ap_soc_npu",
    "semiconductor__advanced_packaging": "semis__packaging_chiplet",
    "semiconductor__eda_material_equipment": "semis__ap_soc_npu",
    "mobile_edge__android_mobile_os": "platform_sw__device_os",
    "mobile_edge__smartphone_compute": None,  # product news: the keywords decide
    "mobile_edge__edge_computing": "cloud_data__edge_cloud",
    "mobile_edge__wearable_health": "health_tech__biosensing",
    "mobile_edge__app_service_ecosystem": "platform_sw__app_ecosystem",
    "display_media__oled_microled": "display_av__display_panel",
    "display_media__display_imaging": "display_av__picture_processing",
    "display_media__tv_media_platform": "display_av__codec_streaming",
    "display_media__xr_spatial_display": "display_av__xr_spatial",
    "display_media__codec_content": "display_av__codec_streaming",
    "network_comms__fiveg_sixg": "connectivity__cellular_5g_6g",
    "network_comms__ran_core": "connectivity__ran_core",
    "network_comms__short_range_wireless": "connectivity__short_range_wireless",
    "network_comms__satellite_ntn": "connectivity__satellite_ntn",
    "network_comms__network_automation_security": "connectivity__network_ops",
    "cloud_infra__public_hybrid_cloud": "cloud_data__cloud_platforms",
    "cloud_infra__kubernetes_container": "cloud_data__infra_ops",
    "cloud_infra__platform_engineering": "cloud_data__infra_ops",
    "cloud_infra__sre_observability": "cloud_data__infra_ops",
    "cloud_infra__finops_green_compute": "cloud_data__infra_ops",
    "software_dev__language_compiler": "platform_sw__developer_tools",
    "software_dev__web_app_framework": "platform_sw__web_cross_platform",
    "software_dev__api_distributed": "platform_sw__developer_tools",
    "software_dev__cicd_testing": "platform_sw__developer_tools",
    "software_dev__developer_experience": "platform_sw__developer_tools",
    "open_source__project_trends": None,
    "open_source__community_health": None,
    "open_source__license_governance": None,
    "open_source__supply_chain_sbom": "security__software_supply_chain",
    "open_source__enterprise_adoption": None,
    "security_privacy__application_security": "security__app_cloud_security",
    "security_privacy__cloud_security": "security__app_cloud_security",
    "security_privacy__device_hardware_security": "security__device_security",
    "security_privacy__identity_zero_trust": "security__identity_auth",
    "security_privacy__privacy_cryptography": "security__privacy_crypto",
    "robotics_auto__humanoid_service_robot": "robotics_mobility__humanoid_embodied",
    "robotics_auto__embodied_ai": "robotics_mobility__humanoid_embodied",
    "robotics_auto__autonomous_adas": "robotics_mobility__autonomous_driving",
    "robotics_auto__drone_unmanned": "robotics_mobility__autonomous_driving",
    "robotics_auto__sensor_control_twin": "robotics_mobility__sensing_digital_twin",
    "manufacturing_supply__smart_factory": "manufacturing__smart_factory",
    "manufacturing_supply__industrial_ai": "manufacturing__smart_factory",
    "manufacturing_supply__scm_logistics": "manufacturing__logistics_automation",
    "manufacturing_supply__quality_yield": "manufacturing__quality_inspection",
    "manufacturing_supply__supply_resilience": None,
    "product_market__consumer_electronics": None,
    "product_market__b2b_enterprise": None,
    "product_market__customer_design": "platform_sw__ux_accessibility",
    "product_market__competition_partnership": None,
    "product_market__pricing_revenue": None,
    "finance_investment__macro_fx": None,
    "finance_investment__capex_investment": None,
    "finance_investment__cost_economics": None,
    "finance_investment__valuation_ir": None,
    "finance_investment__financial_risk": None,
    "policy_ip_standards__technology_regulation": None,
    "policy_ip_standards__ai_governance_ethics": "ai__ai_safety_eval",
    "policy_ip_standards__patent_litigation": None,
    "policy_ip_standards__international_standards": None,
    "policy_ip_standards__export_geopolitics": None,
    "emerging_science__quantum_technology": "frontier__quantum",
    "emerging_science__neuromorphic_photonic": "frontier__neuromorphic_photonic",
    "emerging_science__advanced_materials": "frontier__advanced_materials",
    "emerging_science__battery_energy": "energy__battery_charging",
    "emerging_science__carbon_circularity": "energy__circular_materials",
}

# signal type implied by an old theme (only where the old tree encoded the kind of news)
SIGNAL_MAP: dict[str, str] = {
    "product_market__consumer_electronics": "launch",
    "product_market__b2b_enterprise": "market",
    "product_market__competition_partnership": "market",
    "product_market__pricing_revenue": "market",
    "mobile_edge__smartphone_compute": "launch",
    "finance_investment__macro_fx": "finance",
    "finance_investment__capex_investment": "finance",
    "finance_investment__cost_economics": "finance",
    "finance_investment__valuation_ir": "finance",
    "finance_investment__financial_risk": "finance",
    "policy_ip_standards__technology_regulation": "regulation",
    "policy_ip_standards__ai_governance_ethics": "regulation",
    "policy_ip_standards__export_geopolitics": "regulation",
    "policy_ip_standards__patent_litigation": "ip",
    "policy_ip_standards__international_standards": "standard",
    "open_source__project_trends": "ecosystem",
    "open_source__community_health": "ecosystem",
    "open_source__license_governance": "ecosystem",
    "open_source__enterprise_adoption": "ecosystem",
    "manufacturing_supply__supply_resilience": "supply",
    "manufacturing_supply__scm_logistics": "supply",
}


@dataclass
class ProvisionalResult:
    mapped: int = 0
    from_keywords: int = 0
    without_theme: int = 0


def provisional_labels(
    old_themes: Iterable[str], keys: Iterable[str], registry: dict[str, str]
) -> tuple[list[str], str | None]:
    themes: list[str] = []
    signal: str | None = None
    for old in old_themes:
        if signal is None:
            signal = SIGNAL_MAP.get(old)
        new = THEME_MAP.get(old)
        if new and new not in themes:
            themes.append(new)
    if not themes:
        for key in keys:
            theme = registry.get(key)
            if theme and theme not in themes:
                themes.append(theme)
            if len(themes) == 2:
                break
    return themes[:2], signal


def apply_provisional(session: Session, *, batch: int = 2000) -> ProvisionalResult:
    """Move every ready card that is not on the current tree yet. Idempotent."""
    registry = {
        key: theme
        for key, theme in session.execute(select(Technology.key, Technology.theme_key)).tuples()
        if theme in THEME_KEYS
    }
    result = ProvisionalResult()
    last_id = 0
    while True:
        rows = session.execute(
            select(ItemCard.id, ItemCard.themes, ItemCard.technology_keys)
            .where(
                ItemCard.id > last_id,
                ItemCard.status == CardStatus.READY,
                ~ItemCard.taxonomy_revision.like(f"{TAXONOMY_TREE}.%")
                | ItemCard.taxonomy_revision.is_(None),
            )
            .order_by(ItemCard.id)
            .limit(batch)
        ).all()
        if not rows:
            break
        updates = []
        for card_id, old_themes, keys in rows:
            themes, signal = provisional_labels(old_themes or [], keys or [], registry)
            mapped_directly = any(THEME_MAP.get(old) for old in old_themes or [])
            if themes and mapped_directly:
                result.mapped += 1
            elif themes:
                result.from_keywords += 1
            else:
                result.without_theme += 1
            updates.append(
                {
                    "id": card_id,
                    "themes": themes,
                    "field": themes[0].split("__", 1)[0] if themes else None,
                    "signal_type": signal,
                    "businesses": [],
                    "taxonomy_revision": PROVISIONAL_REVISION,
                }
            )
        session.execute(update(ItemCard), updates)
        last_id = rows[-1][0]
    session.flush()
    return result
