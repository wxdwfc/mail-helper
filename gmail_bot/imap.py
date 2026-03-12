"""IMAP operations for Gmail."""

import email
import email.message
import imaplib
from dataclasses import dataclass
from email.header import decode_header
from html.parser import HTMLParser

from .config import GmailConfig


@dataclass
class Message:
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
    s = _HTMLStripper()
    s.feed(html)
    return s.get_text()


def _decode_header_value(s: str) -> str:
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


def _extract_body(msg: email.message.Message) -> str:
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
            body = _strip_html(raw) if msg.get_content_type() == "text/html" else raw
    return body[:10000]


def _parse_message(uid: str, raw: bytes) -> Message:
    msg = email.message_from_bytes(raw)
    return Message(
        uid=uid,
        subject=_decode_header_value(msg.get("Subject", "(no subject)")),
        sender=_decode_header_value(msg.get("From", "")),
        date=msg.get("Date", ""),
        body=_extract_body(msg),
        message_id=msg.get("Message-ID", "").strip(),
        references=msg.get("References", "").strip(),
    )


def search_by_subject(cfg: GmailConfig, query: str, limit: int = 10) -> list[Message]:
    """Search inbox for messages whose subject contains query. Returns newest first."""
    conn = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port)
    conn.login(cfg.acct, cfg.pwd)
    conn.select("INBOX")
    try:
        if query.isascii():
            escaped = query.replace('"', '\\"')
            _, data = conn.search(None, f'SUBJECT "{escaped}"')
        else:
            # Non-ASCII: use raw IMAP command with UTF-8 literal
            tag = conn._new_tag()
            # Send: <tag> SEARCH CHARSET UTF-8 SUBJECT {<len>}\r\n<utf8-bytes>
            literal = query.encode("utf-8")
            conn.send(tag + b" SEARCH CHARSET UTF-8 SUBJECT {" +
                      str(len(literal)).encode() + b"}\r\n")
            # Wait for continuation response '+'
            while True:
                line = conn.readline()
                if line.startswith(b"+"):
                    break
            conn.send(literal + b"\r\n")
            _, data = conn._command_complete("SEARCH", tag)
        uids = data[0].split()
        if not uids:
            return []
        uids = uids[-limit:]
        results = []
        for uid in reversed(uids):
            _, msg_data = conn.fetch(uid, "(RFC822)")
            results.append(_parse_message(uid.decode(), msg_data[0][1]))
        return results
    finally:
        conn.logout()
