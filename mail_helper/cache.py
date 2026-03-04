import json
from datetime import datetime
from pathlib import Path

from .mail_backend import MailMessage

CACHE_FILE = ".mail_cache.json"


def save_inbox(mails: list[MailMessage], path: str = CACHE_FILE) -> None:
    data = {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "mails": [
            {"uid": m.uid, "subject": m.subject, "sender": m.sender, "date": m.date, "body": m.body}
            for m in mails
        ],
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2))


def load_inbox(path: str = CACHE_FILE) -> tuple[list[MailMessage], str | None]:
    """Return (mails, saved_at) or ([], None) if no cache exists."""
    p = Path(path)
    if not p.exists():
        return [], None
    try:
        data = json.loads(p.read_text())
        mails = [MailMessage(**m) for m in data["mails"]]
        return mails, data.get("saved_at")
    except Exception:
        return [], None
