import email
import imaplib
import smtplib
from dataclasses import dataclass
from email.header import decode_header
from email.mime.text import MIMEText
from html.parser import HTMLParser
from typing import TYPE_CHECKING

from .config import AppConfig

if TYPE_CHECKING:
    from .bulk_plan import RenderedEmail


@dataclass
class MailMessage:
    uid: str
    subject: str
    sender: str
    date: str
    body: str
    message_id: str = ""
    references: str = ""


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

    def get_unread_uids(self, limit: int | None = None) -> list[str]:
        """Return UNSEEN UIDs newest-first without fetching bodies."""
        assert self._conn is not None, "Not connected"
        _, data = self._conn.search(None, "UNSEEN")
        uids = data[0].split()
        if limit:
            uids = uids[-limit:]
        return [uid.decode() for uid in reversed(uids)]

    def get_all_uids(self, limit: int | None = None) -> list[str]:
        """Return ALL UIDs (read + unread) newest-first without fetching bodies."""
        assert self._conn is not None, "Not connected"
        _, data = self._conn.search(None, "ALL")
        uids = data[0].split()
        if limit:
            uids = uids[-limit:]
        return [uid.decode() for uid in reversed(uids)]

    def fetch_unread(self, limit: int | None = None) -> list[MailMessage]:
        return self.fetch_uids(self.get_unread_uids(limit))

    def fetch_uids(self, uids: list[str]) -> list[MailMessage]:
        """Fetch full messages for the given UID list."""
        assert self._conn is not None, "Not connected"
        results = []
        for uid in uids:
            msg = self._fetch_single(uid)
            if msg:
                results.append(msg)
        return results

    def search_keyword(self, keyword: str, limit: int | None = None) -> list[MailMessage]:
        assert self._conn is not None, "Not connected"
        escaped = keyword.replace('"', '\\"')
        is_unicode = not all(ord(c) < 128 for c in keyword)

        uids: list[bytes] | None = None
        if is_unicode:
            # Try CHARSET UTF-8 search (RFC 5738); many servers support it
            try:
                criteria_bytes = f'OR SUBJECT "{escaped}" TEXT "{escaped}"'.encode("utf-8")
                _, data = self._conn.search("UTF-8", criteria_bytes)
                uids = data[0].split()
            except (imaplib.IMAP4.error, Exception):
                uids = None  # fall through to client-side

        if uids is None and not is_unicode:
            # Pure ASCII — plain server-side search
            _, data = self._conn.search(None, f'OR SUBJECT "{escaped}" TEXT "{escaped}"')
            uids = data[0].split()

        if uids is None:
            # Server rejected UTF-8 charset — filter client-side
            return self._client_side_search(keyword, limit)

        if limit:
            uids = uids[-limit:]
        results = []
        for uid in reversed(uids):
            msg = self._fetch_single(uid.decode())
            if msg:
                results.append(msg)
        return results

    def _client_side_search(self, keyword: str, limit: int | None = None) -> list[MailMessage]:
        """Fetch recent emails and match keyword in Python (Unicode-safe fallback)."""
        _, data = self._conn.search(None, "ALL")
        all_uids = data[0].split()[-200:]  # cap at 200 to avoid full-mailbox fetch
        kw = keyword.lower()
        results = []
        for uid in reversed(all_uids):
            msg = self._fetch_single(uid.decode())
            if msg and (kw in msg.subject.lower() or kw in msg.body.lower()):
                results.append(msg)
                if limit and len(results) >= limit:
                    break
        return results

    def mark_seen(self, uid: str) -> None:
        assert self._conn is not None, "Not connected"
        self._conn.uid("STORE", uid, "+FLAGS", r"(\Seen)")

    def mark_unseen(self, uid: str) -> None:
        assert self._conn is not None, "Not connected"
        self._conn.uid("STORE", uid, "-FLAGS", r"(\Seen)")

    def delete_mail(self, uid: str) -> None:
        assert self._conn is not None, "Not connected"
        self._conn.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
        self._conn.expunge()

    def _fetch_single(self, uid: str) -> MailMessage | None:
        try:
            _, data = self._conn.fetch(uid, "(RFC822)")
            raw = data[0][1]
            msg = email.message_from_bytes(raw)
            subject = self._decode_header_value(msg.get("Subject", "(no subject)"))
            sender = self._decode_header_value(msg.get("From", ""))
            date = msg.get("Date", "")
            body = self._extract_body(msg)
            message_id = msg.get("Message-ID", "").strip()
            references = msg.get("References", "").strip()
            return MailMessage(
                uid=uid, subject=subject, sender=sender, date=date, body=body,
                message_id=message_id, references=references,
            )
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

    def send_reply(self, original: MailMessage, subject: str, body: str) -> None:
        """Send a reply that is properly threaded with quoted original body."""
        quoted = "\n".join("> " + line for line in (original.body or "").splitlines())
        attribution = f"On {original.date}, {original.sender} wrote:"
        full_body = f"{body}\n\n{attribution}\n{quoted}"

        msg = MIMEText(full_body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self.config.email
        msg["To"] = original.sender
        if original.message_id:
            msg["In-Reply-To"] = original.message_id
            refs = original.references
            msg["References"] = (refs + " " + original.message_id).strip() if refs else original.message_id
        self._deliver(original.sender.strip(), msg)

    def _deliver(self, recipient: str, msg: MIMEText) -> None:
        if self.config.smtp_use_ssl:
            with smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port) as server:
                server.login(self.config.email, self.config.password)
                server.sendmail(self.config.email, [recipient], msg.as_string())
        else:
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.email, self.config.password)
                server.sendmail(self.config.email, [recipient], msg.as_string())

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

    def send_rendered(self, rendered: list["RenderedEmail"]) -> tuple[list[str], list[str]]:
        sent: list[str] = []
        failed: list[str] = []
        for item in rendered:
            recipient = item.to.strip()
            try:
                self._send_one(recipient, item.subject, item.body)
                sent.append(recipient)
            except Exception:
                failed.append(recipient)
        return sent, failed

    def _send_one(self, recipient: str, subject: str, body: str) -> None:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self.config.email
        msg["To"] = recipient
        self._deliver(recipient, msg)
