from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class AppConfig:
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    smtp_use_ssl: bool
    email: str
    password: str
    ai_api_base: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"
    fetch_count: int = 25
    trash_folder: str = ""  # optional; auto-detected if empty


def load_config(path: str = "config.yaml") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            "Copy config.yaml.example to config.yaml and fill in your credentials."
        )
    with config_path.open() as f:
        data = yaml.safe_load(f)
    return AppConfig(
        imap_host=data["imap_host"],
        imap_port=int(data["imap_port"]),
        smtp_host=data["smtp_host"],
        smtp_port=int(data["smtp_port"]),
        smtp_use_ssl=bool(data.get("smtp_use_ssl", False)),
        email=data["email"],
        password=data["password"],
        ai_api_base=data.get("ai_api_base", "https://api.openai.com/v1"),
        ai_api_key=data.get("ai_api_key", ""),
        ai_model=data.get("ai_model", "gpt-4o-mini"),
        fetch_count=int(data.get("fetch_count", 25)),
        trash_folder=data.get("trash_folder", ""),
    )
