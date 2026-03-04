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


def save_seen_uids(uids: set[str], path: str = CACHE_FILE) -> None:
    """Persist the seen UID set into the existing cache file."""
    p = Path(path)
    try:
        data = json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        data = {}
    data["seen_uids"] = list(uids)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def load_seen_uids(path: str = CACHE_FILE) -> set[str]:
    """Return the persisted seen UID set, or empty set if none."""
    p = Path(path)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text())
        return set(data.get("seen_uids", []))
    except Exception:
        return set()
