from textual.app import ComposeResult
from textual.widgets import DataTable, Label, TabPane
from textual import work

from ...config import AppConfig
from ...mail_backend import IMAPClient, MailMessage
from ..screens.mail_detail import MailDetailModal


class InboxTab(TabPane):
    DEFAULT_CSS = """
    InboxTab {
        padding: 1;
    }
    InboxTab Label {
        margin-bottom: 1;
    }
    """

    def __init__(self, config: AppConfig) -> None:
        super().__init__("Inbox", id="inbox")
        self._config = config
        self._mail_map: dict[str, MailMessage] = {}

    def compose(self) -> ComposeResult:
        yield Label("Unread emails — press R to refresh")
        yield DataTable(id="inbox-table")

    def on_mount(self) -> None:
        table = self.query_one("#inbox-table", DataTable)
        table.add_columns("From", "Subject", "Date")
        table.cursor_type = "row"
        self._load_inbox()

    @work(thread=True, exclusive=True)
    def _load_inbox(self) -> None:
        self.call_from_thread(self._set_status, "Loading…")
        client = IMAPClient(self._config)
        try:
            client.connect()
            mails = client.fetch_unread(limit=self._config.fetch_count)
        except Exception as exc:
            self.call_from_thread(self._set_status, f"Error: {exc}")
            return
        finally:
            client.disconnect()
        self.call_from_thread(self._populate_table, mails)

    def _set_status(self, text: str) -> None:
        self.query_one(Label).update(text)

    def _populate_table(self, mails: list[MailMessage]) -> None:
        table = self.query_one("#inbox-table", DataTable)
        table.clear()
        self._mail_map.clear()
        for m in mails:
            self._mail_map[m.uid] = m
            table.add_row(m.sender[:40], m.subject[:60], m.date[:30], key=m.uid)
        count = len(mails)
        self._set_status(f"{count} unread email{'s' if count != 1 else ''} — press R to refresh")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        uid = str(event.row_key.value)
        mail = self._mail_map.get(uid)
        if mail:
            self.app.push_screen(MailDetailModal(mail))
