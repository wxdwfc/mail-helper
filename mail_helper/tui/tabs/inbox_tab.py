from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Label, ProgressBar, TabPane

from ...ai_analyzer import AnalysisResult, analyze_mails
from ...cache import load_inbox, load_seen_uids, save_inbox, save_seen_uids
from ...config import AppConfig
from ...mail_backend import IMAPClient, MailMessage
from ..screens.mail_detail import MailDetailModal

_PRIORITY_COLORS = {"high": "red", "medium": "yellow", "low": "green"}
_DEL_LABEL = Text("del", style="bold red")


class InboxTab(TabPane):
    BINDINGS = [
        Binding("m", "toggle_read", "Mark Read/Unread"),
        Binding("d", "toggle_delete", "Mark for Delete"),
    ]

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
        self._delete_marked: set[str] = set()
        # saved priority-column label per uid (to restore when unmarking delete)
        self._saved_labels: dict[str, Text] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="toolbar"):
            yield Label("", id="status")
            yield Button("Delete Marked (0)", id="delete-marked-btn", variant="error", disabled=True)
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

        self._seen_uids = load_seen_uids()

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
        elif event.button.id == "delete-marked-btn":
            self._delete_marked_bg(list(self._delete_marked))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None:
            self._cursor_uid = str(event.row_key.value)

    def action_toggle_read(self) -> None:
        if self._cursor_uid:
            seen = self._cursor_uid not in self._seen_uids
            self._mark_seen_bg(self._cursor_uid, seen)

    def action_toggle_delete(self) -> None:
        uid = self._cursor_uid
        if not uid:
            return
        if uid in self._delete_marked:
            # Unmark: restore saved label
            self._delete_marked.discard(uid)
            restored = self._saved_labels.pop(uid, Text(""))
            self._update_priority_cell(uid, restored)
        else:
            # Mark: save current label, show "del"
            self._delete_marked.add(uid)
            current = self._get_priority_label(uid)
            self._saved_labels[uid] = current
            self._update_priority_cell(uid, _DEL_LABEL)
        self._refresh_delete_btn()

    def _get_priority_label(self, uid: str) -> Text:
        """Read the current priority cell value for a uid."""
        table = self.query_one("#inbox-table", DataTable)
        try:
            cell = table.get_cell(uid, "priority")
            if isinstance(cell, Text):
                return cell
        except Exception:
            pass
        return Text("")

    def _update_priority_cell(self, uid: str, label: Text) -> None:
        table = self.query_one("#inbox-table", DataTable)
        try:
            table.update_cell(uid, "priority", label, update_width=True)
        except Exception:
            pass

    def _refresh_delete_btn(self) -> None:
        count = len(self._delete_marked)
        btn = self.query_one("#delete-marked-btn", Button)
        btn.label = f"Delete Marked ({count})"
        btn.disabled = count == 0

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
        total = len(mails)
        self.app.call_from_thread(self._set_status, f"Analyzing {total} emails with AI…")
        self.app.call_from_thread(self._set_analyze_btn, disabled=True)
        try:
            analyze_mails(
                mails,
                self._config,
                on_progress=lambda c, t: self.app.call_from_thread(self._update_progress, c, t),
                on_result=lambda r, c, t: self.app.call_from_thread(self._apply_single_result, r, c, t),
                rules_path="rule.md",
            )
        except Exception as exc:
            self.app.call_from_thread(self._set_status, f"Analysis error: {exc}")
            self.app.call_from_thread(self._set_analyze_btn, disabled=False)
            self.app.call_from_thread(self._hide_progress)
            return
        self.app.call_from_thread(self._set_status, "Analysis complete")
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
        self._delete_marked.clear()
        self._saved_labels.clear()
        self._refresh_delete_btn()
        for m in mails:
            self._mail_map[m.uid] = m
            priority = Text("read", style="dim") if m.uid in self._seen_uids else Text("")
            table.add_row(priority, m.sender[:40], m.subject[:60], m.date[:30], key=m.uid)
        count = len(mails)
        self._set_status(f"{count} unread email{'s' if count != 1 else ''} — press R to refresh")

    def _apply_single_result(self, result: AnalysisResult, current: int, total: int) -> None:
        # Don't overwrite a "del" mark; update saved label instead
        if result.uid in self._delete_marked:
            color = _PRIORITY_COLORS.get(result.importance, "white")
            self._saved_labels[result.uid] = Text(result.importance, style=f"bold {color}")
        else:
            color = _PRIORITY_COLORS.get(result.importance, "white")
            label = Text(result.importance, style=f"bold {color}")
            self._update_priority_cell(result.uid, label)
        self._set_status(f"Analyzing… {current}/{total}")

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
            self._delete_mail_bg_single(uid)

    @work(thread=True)
    def _delete_mail_bg_single(self, uid: str) -> None:
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
    def _delete_marked_bg(self, uids: list[str]) -> None:
        if not uids:
            return
        self.app.call_from_thread(self._set_status, f"Deleting {len(uids)} email(s)…")
        client = IMAPClient(self._config)
        failed: list[str] = []
        deleted: list[str] = []
        try:
            client.connect()
            for uid in uids:
                try:
                    client.delete_mail(uid)
                    deleted.append(uid)
                except Exception:
                    failed.append(uid)
        except Exception as exc:
            self.app.call_from_thread(self._set_status, f"Delete error: {exc}")
            return
        finally:
            client.disconnect()
        for uid in deleted:
            self.app.call_from_thread(self._remove_row, uid)
        if failed:
            self.app.call_from_thread(self._set_status, f"Deleted {len(deleted)}, failed {len(failed)}")
        else:
            self.app.call_from_thread(self._set_status, f"Deleted {len(deleted)} email(s)")

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
        self._delete_marked.discard(uid)
        self._saved_labels.pop(uid, None)
        self._refresh_delete_btn()

    def _apply_seen_state(self, uid: str, seen: bool) -> None:
        table = self.query_one("#inbox-table", DataTable)
        if seen:
            self._seen_uids.add(uid)
            label = Text("read", style="dim")
        else:
            self._seen_uids.discard(uid)
            label = Text("")
        save_seen_uids(self._seen_uids)
        # If marked for delete, update saved label instead of the cell
        if uid in self._delete_marked:
            self._saved_labels[uid] = label
        else:
            try:
                table.update_cell(uid, "priority", label, update_width=True)
            except Exception:
                pass
