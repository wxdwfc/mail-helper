from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static
from textual.containers import Vertical, ScrollableContainer

from ...mail_backend import MailMessage


class MailDetailModal(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Close")]

    DEFAULT_CSS = """
    MailDetailModal {
        align: center middle;
    }
    MailDetailModal > Vertical {
        background: $surface;
        border: tall $primary;
        width: 90%;
        height: 90%;
        padding: 1 2;
    }
    MailDetailModal .meta {
        color: $text-muted;
        margin-bottom: 1;
    }
    MailDetailModal .subject {
        text-style: bold;
        margin-bottom: 1;
    }
    MailDetailModal ScrollableContainer {
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    MailDetailModal Button {
        margin-top: 1;
        dock: bottom;
    }
    """

    def __init__(self, mail: MailMessage) -> None:
        super().__init__()
        self._mail = mail

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"From:    {self._mail.sender}", classes="meta")
            yield Label(f"Date:    {self._mail.date}", classes="meta")
            yield Label(f"Subject: {self._mail.subject}", classes="subject")
            with ScrollableContainer():
                yield Static(self._mail.body or "(no body)")
            yield Button("Close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()
