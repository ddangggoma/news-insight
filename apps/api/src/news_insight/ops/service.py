"""Alert episodes from check findings, and e-mail for newly opened critical/warning alerts."""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_insight.auth.mailer import send_email
from news_insight.config import Settings
from news_insight.ops.checks import Finding
from news_insight.ops.models import OpsAlert, Severity

log = logging.getLogger(__name__)
NOTIFY = (Severity.CRITICAL, Severity.WARNING)
# shown on the console only (2026-10-08, no mail or push alerts for these)
CONSOLE_ONLY = frozenset({"host_memory", "qwen_unloaded", "cards_zero"})


@dataclass
class SyncResult:
    opened: list[OpsAlert] = field(default_factory=list)
    resolved: list[OpsAlert] = field(default_factory=list)
    open: list[OpsAlert] = field(default_factory=list)


def open_alerts(session: Session) -> list[OpsAlert]:
    return list(
        session.scalars(
            select(OpsAlert).where(OpsAlert.resolved_at.is_(None)).order_by(OpsAlert.opened_at)
        )
    )


def sync_alerts(session: Session, findings: list[Finding], *, now: datetime) -> SyncResult:
    current = {alert.key: alert for alert in open_alerts(session)}
    result = SyncResult()
    seen: set[str] = set()
    for finding in findings:
        seen.add(finding.key)
        alert = current.get(finding.key)
        if alert is None:
            alert = OpsAlert(
                key=finding.key,
                severity=finding.severity,
                title=finding.title,
                detail=finding.detail,
                opened_at=now,
                last_seen_at=now,
            )
            session.add(alert)
            result.opened.append(alert)
        else:
            alert.severity, alert.title, alert.detail = (
                finding.severity,
                finding.title,
                finding.detail,
            )
            alert.last_seen_at = now
        result.open.append(alert)
    for key, alert in current.items():
        if key not in seen:
            alert.resolved_at = now
            result.resolved.append(alert)
    session.flush()
    return result


def notify(settings: Settings, result: SyncResult, *, now: datetime) -> bool:
    """One e-mail per run listing newly opened critical/warning alerts (SMTP optional)."""
    fresh = [
        alert
        for alert in result.opened
        if alert.severity in NOTIFY and alert.key not in CONSOLE_ONLY
    ]
    if not fresh:
        return False
    lines = [f"[{a.severity.value}] {a.title}\n  {a.detail}".rstrip() for a in fresh]
    body = "\n\n".join(lines) + f"\n\n콘솔: {settings.public_base_url.rstrip('/')}/console/alerts\n"
    sent = send_email(
        settings, to=settings.admin_email, subject=f"[Daily IT] 운영 알림 {len(fresh)}건", body=body
    )
    if sent:
        for alert in fresh:
            alert.notified_at = now
    else:
        for alert in fresh:
            log.warning("ops alert %s: %s", alert.key, alert.title)
    return sent
