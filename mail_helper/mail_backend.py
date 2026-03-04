import email
import imaplib
import re
import smtplib
from dataclasses import dataclass
from email.header import decode_header
from email.mime.text import MIMEText
from html.parser import HTMLParser

from .config import AppConfig


@dataclass
class MailMessage:
    uid: str
    subject: str
    sender: str
    date: str
    body: str


class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _strip_html(html: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


class IMAPClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._conn: imaplib.IMAP4_SSL | None = None

    def connect(self) -> None:
        self._conn = imaplib.IMAP4_SSL(self.config.imap_host, self.config.imap_port)
        self._conn.login(self.config.email, self.config.password)
        self._conn.select("INBOX")

    def disconnect(self) -> None:
        try:
            if self._conn:
                self._conn.logout()
        except Exception:
            pass
        self._conn = None

    def fetch_unread(self, limit: int | None = None) -> list[MailMessage]:
        assert self._conn is not None, "Not connected"
        _, data = self._conn.search(None, "UNSEEN")
        uids = data[0].split()
        if limit:
            uids = uids[-limit:]  # newest at end
        uids = list(reversed(uids))  # newest-first
        results = []
        for uid in uids:
            msg = self._fetch_single(uid.decode())
            if msg:
                results.append(msg)
        return results

    def search_keyword(self, keyword: str, limit: int | None = None) -> list[MailMessage]:
        assert self._conn is not None, "Not connected"
        escaped = keyword.replace('"', '\\"')
        criteria = f'OR SUBJECT "{escaped}" TEXT "{escaped}"'
        _, data = self._conn.search(None, criteria)
        uids = data[0].split()
        if limit:
            uids = uids[-limit:]
        uids = list(reversed(uids))
        results = []
        for uid in uids:
            msg = self._fetch_single(uid.decode())
            if msg:
                results.append(msg)
        return results

    def _fetch_single(self, uid: str) -> MailMessage | None:
        try:
            _, data = self._conn.fetch(uid, "(RFC822)")
            raw = data[0][1]
            msg = email.message_from_bytes(raw)
            subject = self._decode_header_value(msg.get("Subject", "(no subject)"))
            sender = self._decode_header_value(msg.get("From", ""))
            date = msg.get("Date", "")
            body = self._extract_body(msg)
            return MailMessage(uid=uid, subject=subject, sender=sender, date=date, body=body)
        except Exception:
            return None

    def _decode_header_value(self, s: str) -> str:
        if not s:
            return ""
        parts = decode_header(s)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                try:
                    decoded.append(part.decode(charset or "utf-8", errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    decoded.append(part.decode("utf-8", errors="replace"))
            else:
                decoded.append(part)
        return "".join(decoded)

    def _extract_body(self, msg: email.message.Message) -> str:
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                cd = str(part.get("Content-Disposition", ""))
                if "attachment" in cd:
                    continue
                if ct == "text/plain":
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
                if ct == "text/html" and not body:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    body = _strip_html(payload.decode(charset, errors="replace"))
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                raw = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    body = _strip_html(raw)
                else:
                    body = raw
        return body[:10000]


class SMTPClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def send_bulk(
        self, recipients: list[str], subject: str, body: str
    ) -> tuple[list[str], list[str]]:
        sent: list[str] = []
        failed: list[str] = []
        for recipient in recipients:
            try:
                self._send_one(recipient.strip(), subject, body)
                sent.append(recipient)
            except Exception:
                failed.append(recipient)
        return sent, failed

    def _send_one(self, recipient: str, subject: str, body: str) -> None:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self.config.email
        msg["To"] = recipient

        if self.config.smtp_use_ssl:
            with smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port) as server:
                server.login(self.config.email, self.config.password)
                server.sendmail(self.config.email, [recipient], msg.as_string())
        else:
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.email, self.config.password)
                server.sendmail(self.config.email, [recipient], msg.as_string())
