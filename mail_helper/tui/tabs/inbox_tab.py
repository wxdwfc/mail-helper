from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Label, TabPane

from ...ai_analyzer import AnalysisResult, analyze_mails
from ...cache import load_inbox, save_inbox
from ...config import AppConfig
from ...mail_backend import IMAPClient, MailMessage
from ..screens.mail_detail import MailDetailModal

_PRIORITY_COLORS = {"high": "red", "medium": "yellow", "low": "green"}


class InboxTab(TabPane):
    DEFAULT_CSS = """
    InboxTab {
        padding: 1;
    }
    InboxTab #toolbar {
        height: auto;
        margin-bottom: 1;
    }
    InboxTab #status {
        width: 1fr;
        margin-top: 1;
    }
    InboxTab Button {
        margin-left: 1;
    }
    """

    def __init__(self, config: AppConfig) -> None:
        super().__init__("Inbox", id="inbox")
        self._config = config
        self._mail_map: dict[str, MailMessage] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="toolbar"):
            yield Label("", id="status")
            yield Button("Analyze with AI", id="analyze-btn", variant="primary")
        yield DataTable(id="inbox-table")

    def on_mount(self) -> None:
        table = self.query_one("#inbox-table", DataTable)
        table.add_column("Priority", key="priority")
        table.add_column("From", key="from")
        table.add_column("Subject", key="subject")
        table.add_column("Date", key="date")
        table.cursor_type = "row"

        # Show cached emails instantly, then refresh in background
        cached, saved_at = load_inbox()
        if cached:
            self._populate_table(cached)
            self._set_status(f"Cached ({saved_at}) — refreshing…")
            self._load_inbox(background=True)
        else:
            self._load_inbox(background=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "analyze-btn":
            self._run_analysis()

    @work(thread=True, exclusive=True)
    def _load_inbox(self, background: bool = False) -> None:
        if not background:
            self.app.call_from_thread(self._set_status, "Loading…")
        client = IMAPClient(self._config)
        try:
            client.connect()
            uids = client.get_unread_uids(limit=self._config.fetch_count)

            # Reuse cached bodies for UIDs we already have
            cached_map = {m.uid: m for m in self._mail_map.values()}
            new_uids = [uid for uid in uids if uid not in cached_map]
            new_mails = client.fetch_uids(new_uids)
        except Exception as exc:
            self.app.call_from_thread(self._set_status, f"Error: {exc}")
            return
        finally:
            client.disconnect()

        # Merge: new emails first, then still-unread cached ones
        new_map = {m.uid: m for m in new_mails}
        merged = [new_map.get(uid) or cached_map[uid] for uid in uids]
        save_inbox(merged)
        self.app.call_from_thread(self._populate_table, merged)

    @work(thread=True, exclusive=True)
    def _run_analysis(self) -> None:
        mails = list(self._mail_map.values())
        if not mails:
            self.app.call_from_thread(self._set_status, "No emails to analyze.")
            return
        self.app.call_from_thread(self._set_status, f"Analyzing {len(mails)} emails with AI…")
        self.app.call_from_thread(self._set_analyze_btn, disabled=True)
        try:
            results = analyze_mails(mails, self._config)
        except Exception as exc:
            self.app.call_from_thread(self._set_status, f"Analysis error: {exc}")
            self.app.call_from_thread(self._set_analyze_btn, disabled=False)
            return
        self.app.call_from_thread(self._apply_analysis, results)
        self.app.call_from_thread(self._set_analyze_btn, disabled=False)

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Label).update(text)

    def _set_analyze_btn(self, disabled: bool) -> None:
        self.query_one("#analyze-btn", Button).disabled = disabled

    def _populate_table(self, mails: list[MailMessage]) -> None:
        table = self.query_one("#inbox-table", DataTable)
        table.clear()
        self._mail_map.clear()
        for m in mails:
            self._mail_map[m.uid] = m
            table.add_row("", m.sender[:40], m.subject[:60], m.date[:30], key=m.uid)
        count = len(mails)
        self._set_status(f"{count} unread email{'s' if count != 1 else ''} — press R to refresh")

    def _apply_analysis(self, results: list[AnalysisResult]) -> None:
        table = self.query_one("#inbox-table", DataTable)
        for r in results:
            color = _PRIORITY_COLORS.get(r.importance, "white")
            label = Text(r.importance, style=f"bold {color}")
            try:
                table.update_cell(r.uid, "priority", label, update_width=True)
            except Exception:
                pass
        self._set_status("Analysis complete — sorted by AI priority")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        uid = str(event.row_key.value)
        mail = self._mail_map.get(uid)
        if mail:
            self.app.push_screen(MailDetailModal(mail))
