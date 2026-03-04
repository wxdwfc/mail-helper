from pathlib import Path

import click
from click.exceptions import Exit
from rich.console import Console
from rich.table import Table

from .ai_analyzer import analyze_mails
from .bulk_plan import BulkPlanError, load_bulk_plan, preview_rows, render_bulk_plan
from .cache import load_inbox, save_inbox
from .config import load_config
from .mail_backend import IMAPClient, SMTPClient

console = Console()


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
        save_inbox(mails)
        console.print("[dim]Saved to cache[/dim]")


@cli.command()
@click.option("--fresh", is_flag=True, default=False, help="Re-fetch from server instead of cache")
def analyze(fresh: bool) -> None:
    """Analyze emails with AI and show prioritized results."""
    config = load_config()

    if fresh:
        client = IMAPClient(config)
        try:
            with console.status("Fetching emails…"):
                client.connect()
                mails = client.fetch_unread(limit=config.fetch_count)
        finally:
            client.disconnect()
        save_inbox(mails)
    else:
        mails, saved_at = load_inbox()
        if not mails:
            console.print("[yellow]No cache found — run 'inbox' first or use --fresh[/yellow]")
            return
        console.print(f"[dim]Loaded {len(mails)} emails from cache (saved {saved_at})[/dim]")

    if not mails:
        console.print("[yellow]No emails to analyze.[/yellow]")
        return

    with console.status("Analyzing with AI…"):
        results = analyze_mails(mails, config)

    mail_map = {m.uid: m for m in mails}
    colors = {"high": "red", "medium": "yellow", "low": "green"}

    table = Table(title="AI-Prioritized Emails", show_lines=True)
    table.add_column("Priority", width=8)
    table.add_column("Subject", min_width=30)
    table.add_column("Reason", min_width=30)
    table.add_column("Action", min_width=30)

    for r in results:
        m = mail_map.get(r.uid)
        subject = m.subject[:50] if m else r.uid
        color = colors.get(r.importance, "white")
        table.add_row(
            f"[{color}]{r.importance}[/{color}]",
            subject,
            r.reason[:60],
            r.action[:60],
        )

    console.print(table)


@cli.command(name="bulk-send")
@click.option(
    "--plan",
    "plan_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to bulk-send TOML plan.",
)
@click.option(
    "--yes",
    "send_now",
    is_flag=True,
    default=False,
    help="Actually send emails. Default mode is dry-run preview.",
)
@click.option(
    "--preview-limit",
    default=10,
    show_default=True,
    type=int,
    help="How many rendered emails to show in preview.",
)
def bulk_send(plan_path: Path, send_now: bool, preview_limit: int) -> None:
    """Preview or send emails from a TOML bulk plan."""
    if preview_limit < 0:
        raise click.BadParameter("must be >= 0", param_hint="--preview-limit")

    resolved_plan = plan_path.resolve()
    try:
        plan = load_bulk_plan(str(resolved_plan))
        rendered = render_bulk_plan(plan, base_dir=resolved_plan.parent)
    except BulkPlanError as exc:
        raise click.ClickException(str(exc)) from exc

    total = len(rendered)
    if total == 0:
        console.print("[yellow]Plan parsed successfully, but there are no emails to send.[/yellow]")
        return

    preview = preview_rows(rendered, limit=preview_limit)
    table = Table(title=f"Bulk Send Preview ({total})", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("To", min_width=24)
    table.add_column("Subject", min_width=28)
    table.add_column("Template", min_width=12)

    for i, (to, subject, template_id) in enumerate(preview, start=1):
        table.add_row(str(i), to[:50], subject[:70], template_id[:30])

    console.print(table)
    if total > len(preview):
        console.print(f"[dim]Showing {len(preview)} of {total} rendered emails.[/dim]")

    if not send_now:
        console.print("[yellow]Dry run only. Re-run with --yes to send.[/yellow]")
        return

    config = load_config()
    client = SMTPClient(config)
    with console.status(f"Sending {total} email(s)…"):
        sent, failed = client.send_rendered(rendered)

    if sent:
        console.print(f"[green]Sent {len(sent)} email(s).[/green]")
    if failed:
        console.print(f"[red]Failed {len(failed)} email(s): {', '.join(failed)}[/red]")
        raise Exit(1)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
