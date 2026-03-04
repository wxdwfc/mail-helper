from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent

from ..config import AppConfig
from .tabs.compose_tab import ComposeTab
from .tabs.inbox_tab import InboxTab
from .tabs.search_tab import SearchTab


class MailHelperApp(App):
    TITLE = "Mail Helper"
    BINDINGS = [
        Binding("r", "refresh_inbox", "Refresh Inbox"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            yield InboxTab(self._config)
            yield SearchTab(self._config)
            yield ComposeTab(self._config)
        yield Footer()

    def action_refresh_inbox(self) -> None:
        try:
            inbox = self.query_one("#inbox", InboxTab)
            inbox._load_inbox()
        except Exception:
            pass
