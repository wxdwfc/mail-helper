import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .ai_analyzer import analyze_mails
from .config import load_config
from .mail_backend import IMAPClient, MailMessage

CACHE_FILE = ".mail_cache.json"
console = Console()


def _mails_to_dicts(mails: list[MailMessage]) -> list[dict]:
    return [
        {"uid": m.uid, "subject": m.subject, "sender": m.sender, "date": m.date, "body": m.body}
        for m in mails
    ]


def _dicts_to_mails(data: list[dict]) -> list[MailMessage]:
    return [MailMessage(**d) for d in data]


@click.group()
def cli() -> None:
    """Mail Helper CLI"""


@cli.command()
@click.option("--limit", default=20, show_default=True, help="Max emails to fetch")
@click.option("--save/--no-save", default=True, show_default=True, help="Save results to cache")
def inbox(limit: int, save: bool) -> None:
    """Fetch unread emails and display them."""
    config = load_config()
    client = IMAPClient(config)
    try:
        with console.status("Connecting to IMAP…"):
            client.connect()
        with console.status(f"Fetching up to {limit} unread emails…"):
            mails = client.fetch_unread(limit=limit)
    finally:
        client.disconnect()

    if not mails:
        console.print("[yellow]No unread emails found.[/yellow]")
        return

    table = Table(title=f"Unread Emails ({len(mails)})", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("From", min_width=20)
    table.add_column("Subject", min_width=30)
    table.add_column("Date", min_width=20)

    for i, m in enumerate(mails, 1):
        table.add_row(str(i), m.sender[:40], m.subject[:60], m.date[:30])

    console.print(table)

    if save:
        Path(CACHE_FILE).write_text(json.dumps(_mails_to_dicts(mails), ensure_ascii=False, indent=2))
        console.print(f"[dim]Saved to {CACHE_FILE}[/dim]")


@cli.command()
@click.option("--fresh", is_flag=True, default=False, help="Re-fetch from server instead of cache")
def analyze(fresh: bool) -> None:
    """Analyze emails with AI and show prioritized results."""
    config = load_config()

    if fresh or not Path(CACHE_FILE).exists():
        client = IMAPClient(config)
        try:
            with console.status("Fetching emails…"):
                client.connect()
                mails = client.fetch_unread(limit=config.fetch_count)
        finally:
            client.disconnect()
        Path(CACHE_FILE).write_text(json.dumps(_mails_to_dicts(mails), ensure_ascii=False, indent=2))
    else:
        data = json.loads(Path(CACHE_FILE).read_text())
        mails = _dicts_to_mails(data)
        console.print(f"[dim]Loaded {len(mails)} emails from cache[/dim]")

    if not mails:
        console.print("[yellow]No emails to analyze.[/yellow]")
        return

    with console.status("Analyzing with AI…"):
        results = analyze_mails(mails, config)

    # Build uid → mail lookup
    mail_map = {m.uid: m for m in mails}

    COLORS = {"high": "red", "medium": "yellow", "low": "green"}

    table = Table(title="AI-Prioritized Emails", show_lines=True)
    table.add_column("Priority", width=8)
    table.add_column("Subject", min_width=30)
    table.add_column("Reason", min_width=30)
    table.add_column("Action", min_width=30)

    for r in results:
        m = mail_map.get(r.uid)
        subject = m.subject[:50] if m else r.uid
        color = COLORS.get(r.importance, "white")
        table.add_row(
            f"[{color}]{r.importance}[/{color}]",
            subject,
            r.reason[:60],
            r.action[:60],
        )

    console.print(table)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
