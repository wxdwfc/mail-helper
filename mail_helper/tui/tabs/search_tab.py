from textual.app import ComposeResult
from textual.widgets import Button, DataTable, Input, Label, TabPane
from textual import work

from ...config import AppConfig
from ...mail_backend import IMAPClient, MailMessage
from ..screens.mail_detail import MailDetailModal


class SearchTab(TabPane):
    DEFAULT_CSS = """
    SearchTab {
        padding: 1;
    }
    SearchTab #search-row {
        height: auto;
        margin-bottom: 1;
    }
    SearchTab Input {
        width: 1fr;
    }
    SearchTab Button {
        width: auto;
        margin-left: 1;
    }
    """

    def __init__(self, config: AppConfig) -> None:
        super().__init__("Search", id="search")
        self._config = config
        self._mail_map: dict[str, MailMessage] = {}

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal
        with Horizontal(id="search-row"):
            yield Input(placeholder="Search keyword…", id="search-input")
            yield Button("Search", variant="primary", id="search-btn")
        yield Label("Enter a keyword and press Search or Enter")
        yield DataTable(id="search-table")

    def on_mount(self) -> None:
        table = self.query_one("#search-table", DataTable)
        table.add_columns("From", "Subject", "Date")
        table.cursor_type = "row"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "search-btn":
            self._do_search()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search-input":
            self._do_search()

    def _do_search(self) -> None:
        keyword = self.query_one("#search-input", Input).value.strip()
        if keyword:
            self._run_search(keyword)

    @work(thread=True, exclusive=True)
    def _run_search(self, keyword: str) -> None:
        self.app.call_from_thread(self._set_status, f'Searching for "{keyword}"…')
        client = IMAPClient(self._config)
        try:
            client.connect()
            mails = client.search_keyword(keyword, limit=self._config.fetch_count)
        except Exception as exc:
            self.app.call_from_thread(self._set_status, f"Error: {exc}")
            return
        finally:
            client.disconnect()
        self.app.call_from_thread(self._populate_table, mails, keyword)

    def _set_status(self, text: str) -> None:
        self.query_one(Label).update(text)

    def _populate_table(self, mails: list[MailMessage], keyword: str) -> None:
        table = self.query_one("#search-table", DataTable)
        table.clear()
        self._mail_map.clear()
        for m in mails:
            self._mail_map[m.uid] = m
            table.add_row(m.sender[:40], m.subject[:60], m.date[:30], key=m.uid)
        count = len(mails)
        self._set_status(f'{count} result{"s" if count != 1 else ""} for "{keyword}"')

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        uid = str(event.row_key.value)
        mail = self._mail_map.get(uid)
        if mail:
            self.app.push_screen(MailDetailModal(mail))
