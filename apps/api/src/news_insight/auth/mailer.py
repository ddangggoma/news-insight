"""Magic-link delivery over SMTP. Without SMTP settings the CLI prints links instead."""

import logging
import smtplib
import ssl
from email.message import EmailMessage

from news_insight.config import Settings

log = logging.getLogger(__name__)


def login_url(settings: Settings, token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/login/verify?token={token}"


def build_message(settings: Settings, *, to: str, url: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = "Daily IT Intelligence 관리자 로그인 링크"
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = to
    message.set_content(
        "아래 링크를 열고 '로그인' 버튼을 누르면 운영 콘솔에 접속합니다.\n\n"
        f"{url}\n\n"
        "링크는 15분 동안 한 번만 사용할 수 있습니다. 요청하지 않았다면 이 메일을 무시하세요.\n"
    )
    return message


def send_login_link(settings: Settings, *, to: str, url: str) -> bool:
    if not settings.smtp_host:
        log.warning("magic link issued but SMTP is not configured; use `news-insight admin link`")
        return False
    message = build_message(settings, to=to, url=url)
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
        log.error("magic link delivery failed: %s", type(exc).__name__)
        return False
    return True


def _deliver(smtp: smtplib.SMTP, settings: Settings, message: EmailMessage) -> None:
    if settings.smtp_user:
        smtp.login(settings.smtp_user, settings.smtp_password)
    smtp.send_message(message)
