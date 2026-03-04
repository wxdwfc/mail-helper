from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Label, ProgressBar, TabPane

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
    InboxTab #analysis-progress {
        display: none;
        height: 1;
        margin-top: 1;
    }
    """

    def __init__(self, config: AppConfig) -> None:
        super().__init__("Inbox", id="inbox")
        self._config = config
        self._mail_map: dict[str, MailMessage] = {}
        self._seen_uids: set[str] = set()
        self._cursor_uid: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="toolbar"):
            yield Label("", id="status")
            yield Button("Mark Read", id="mark-btn", variant="warning")
            yield Button("Analyze with AI", id="analyze-btn", variant="primary")
        yield ProgressBar(id="analysis-progress", total=1, show_eta=False)
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
        elif event.button.id == "mark-btn" and self._cursor_uid:
            seen = self._cursor_uid not in self._seen_uids
            self._mark_seen_bg(self._cursor_uid, seen)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None:
            self._cursor_uid = str(event.row_key.value)
            is_seen = self._cursor_uid in self._seen_uids
            self.query_one("#mark-btn", Button).label = "Mark Unread" if is_seen else "Mark Read"

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
        mails = [m for m in self._mail_map.values() if m.uid not in self._seen_uids]
        if not mails:
            self.app.call_from_thread(self._set_status, "No emails to analyze.")
            return
        self.app.call_from_thread(self._set_status, f"Analyzing {len(mails)} emails with AI…")
        self.app.call_from_thread(self._set_analyze_btn, disabled=True)
        try:
            results = analyze_mails(
                mails,
                self._config,
                on_progress=lambda c, t: self.app.call_from_thread(self._update_progress, c, t),
            )
        except Exception as exc:
            self.app.call_from_thread(self._set_status, f"Analysis error: {exc}")
            self.app.call_from_thread(self._set_analyze_btn, disabled=False)
            self.app.call_from_thread(self._hide_progress)
            return
        self.app.call_from_thread(self._apply_analysis, results)
        self.app.call_from_thread(self._set_analyze_btn, disabled=False)

    def _update_progress(self, current: int, total: int) -> None:
        bar = self.query_one("#analysis-progress", ProgressBar)
        if current == 1:
            bar.total = total
            bar.progress = 0
            bar.display = True
        bar.advance(1)
        if current == total:
            bar.display = False

    def _hide_progress(self) -> None:
        self.query_one("#analysis-progress", ProgressBar).display = False

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
            self.app.push_screen(
                MailDetailModal(mail, self._config),
                callback=lambda result, u=uid: self._on_detail_closed(u, result),
            )

    def _on_detail_closed(self, uid: str, result: str | None) -> None:
        if result == "delete":
            self._delete_mail_bg(uid)

    @work(thread=True)
    def _delete_mail_bg(self, uid: str) -> None:
        client = IMAPClient(self._config)
        try:
            client.connect()
            client.delete_mail(uid)
        except Exception as exc:
            self.app.call_from_thread(self._set_status, f"Delete error: {exc}")
            return
        finally:
            client.disconnect()
        self.app.call_from_thread(self._remove_row, uid)

    @work(thread=True)
    def _mark_seen_bg(self, uid: str, seen: bool) -> None:
        client = IMAPClient(self._config)
        try:
            client.connect()
            if seen:
                client.mark_seen(uid)
            else:
                client.mark_unseen(uid)
        except Exception as exc:
            self.app.call_from_thread(self._set_status, f"Mark error: {exc}")
            return
        finally:
            client.disconnect()
        self.app.call_from_thread(self._apply_seen_state, uid, seen)

    def _remove_row(self, uid: str) -> None:
        table = self.query_one("#inbox-table", DataTable)
        try:
            table.remove_row(uid)
        except Exception:
            pass
        self._mail_map.pop(uid, None)
        self._seen_uids.discard(uid)

    def _apply_seen_state(self, uid: str, seen: bool) -> None:
        table = self.query_one("#inbox-table", DataTable)
        if seen:
            self._seen_uids.add(uid)
            label = Text("read", style="dim")
        else:
            self._seen_uids.discard(uid)
            label = Text("")
        try:
            table.update_cell(uid, "priority", label, update_width=True)
        except Exception:
            pass
        if uid == self._cursor_uid:
            self.query_one("#mark-btn", Button).label = "Mark Unread" if seen else "Mark Read"
