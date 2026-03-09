"""SMTP operations for Gmail."""

import smtplib
from email.mime.text import MIMEText

from .config import GmailConfig
from .imap import Message


def send_mail(
    cfg: GmailConfig,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
) -> None:
    """Send a plain-text email."""
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = cfg.acct
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)

    all_recipients = to + (cc or [])
    _deliver(cfg, all_recipients, msg)
    print(f"Sent to: {', '.join(all_recipients)}")


def reply_thread(
    cfg: GmailConfig,
    original: Message,
    body: str,
    to: list[str] | None = None,
    cc: list[str] | None = None,
) -> None:
    """Send a threaded reply to an existing message."""
    recipients = to if to else [original.sender]
    subject = original.subject
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = cfg.acct
    msg["To"] = ", ".join(recipients)
    if cc:
        msg["Cc"] = ", ".join(cc)

    if original.message_id:
        msg["In-Reply-To"] = original.message_id
        refs = original.references
        msg["References"] = (
            f"{refs} {original.message_id}".strip() if refs else original.message_id
        )

    all_recipients = recipients + (cc or [])
    _deliver(cfg, all_recipients, msg)
    print(f"Reply sent to: {', '.join(all_recipients)}")


def _deliver(cfg: GmailConfig, recipients: list[str], msg: MIMEText) -> None:
    with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port) as server:
        server.login(cfg.acct, cfg.pwd)
        server.sendmail(cfg.acct, recipients, msg.as_string())
