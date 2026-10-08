"""Mail to the admin over SMTP: operational alerts and sign-up requests (plan 14)."""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from news_insight.config import Settings

log = logging.getLogger(__name__)


def send_email(settings: Settings, *, to: str, subject: str, body: str) -> bool:
    """Plain-text mail to the admin (ops alerts, sign-ups). False when SMTP is not configured."""
    if not settings.smtp_host:
        return False
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = to
    message.set_content(body)
    return _send(settings, message)


def _send(settings: Settings, message: EmailMessage) -> bool:
    context = ssl.create_default_context()
    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, context=context, timeout=20
            ) as smtp:
                _deliver(smtp, settings, message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                smtp.starttls(context=context)
                _deliver(smtp, settings, message)
    except (OSError, smtplib.SMTPException) as exc:
        log.error("mail delivery failed: %s", type(exc).__name__)
        return False
    return True


def _deliver(smtp: smtplib.SMTP, settings: Settings, message: EmailMessage) -> None:
    if settings.smtp_user:
        smtp.login(settings.smtp_user, settings.smtp_password)
    smtp.send_message(message)
