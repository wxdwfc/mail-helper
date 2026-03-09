"""Load gmail.yaml config."""

from dataclasses import dataclass
from pathlib import Path

import yaml

GMAIL_IMAP = "imap.gmail.com"
GMAIL_SMTP = "smtp.gmail.com"
IMAP_PORT = 993
SMTP_PORT = 465


@dataclass
class GmailConfig:
    acct: str
    pwd: str
    imap_host: str = GMAIL_IMAP
    imap_port: int = IMAP_PORT
    smtp_host: str = GMAIL_SMTP
    smtp_port: int = SMTP_PORT


def load_config(path: str = "gmail.yaml") -> GmailConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"{path} not found. Create it with acct/pwd fields.")
    data = yaml.safe_load(p.read_text())
    return GmailConfig(acct=data["acct"], pwd=data["pwd"])
