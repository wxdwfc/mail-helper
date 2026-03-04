from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static
from textual.containers import Horizontal, Vertical, ScrollableContainer

from ...config import AppConfig
from ...mail_backend import MailMessage


class MailDetailModal(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss_none", "Close")]

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
    MailDetailModal #button-bar {
        height: auto;
        margin-top: 1;
        dock: bottom;
    }
    MailDetailModal #button-bar Button {
        margin-right: 1;
    }
    """

    def __init__(self, mail: MailMessage, config: AppConfig, is_seen: bool = False) -> None:
        super().__init__()
        self._mail = mail
        self._config = config
        self._is_seen = is_seen

    def compose(self) -> ComposeResult:
        mark_label = "Mark Unread" if self._is_seen else "Mark Read"
        with Vertical():
            yield Label(f"From:    {self._mail.sender}", classes="meta")
            yield Label(f"Date:    {self._mail.date}", classes="meta")
            yield Label(f"Subject: {self._mail.subject}", classes="subject")
            with ScrollableContainer():
                yield Static(self._mail.body or "(no body)")
            with Horizontal(id="button-bar"):
                yield Button("Reply", id="reply-btn", variant="primary")
                yield Button("Delete", id="delete-btn", variant="error")
                yield Button(mark_label, id="mark-btn", variant="warning")
                yield Button("Close", id="close-btn")

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "reply-btn":
            from .reply_modal import ReplyModal
            self.app.push_screen(ReplyModal(self._mail, self._config))
        elif event.button.id == "delete-btn":
            self.dismiss("delete")
        elif event.button.id == "mark-btn":
            self.dismiss("mark_unread" if self._is_seen else "mark_read")
        elif event.button.id == "close-btn":
            self.dismiss(None)
