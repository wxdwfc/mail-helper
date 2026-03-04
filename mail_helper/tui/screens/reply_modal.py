from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, TextArea
from textual.containers import Horizontal, Vertical

from ...config import AppConfig
from ...mail_backend import MailMessage, SMTPClient


class ReplyModal(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    ReplyModal {
        align: center middle;
    }
    ReplyModal > Vertical {
        background: $surface;
        border: tall $primary;
        width: 80%;
        height: 80%;
        padding: 1 2;
    }
    ReplyModal Label {
        margin-bottom: 1;
    }
    ReplyModal Input {
        margin-bottom: 1;
    }
    ReplyModal TextArea {
        height: 1fr;
        margin-bottom: 1;
    }
    ReplyModal #error-msg {
        color: $error;
    }
    ReplyModal #button-bar {
        height: auto;
        dock: bottom;
        margin-top: 1;
    }
    ReplyModal #button-bar Button {
        margin-right: 1;
    }
    """

    def __init__(self, mail: MailMessage, config: AppConfig) -> None:
        super().__init__()
        self._mail = mail
        self._config = config

    def compose(self) -> ComposeResult:
        subject = self._mail.subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        with Vertical():
            yield Label(f"To: {self._mail.sender}", id="to-label")
            yield Input(value=subject, placeholder="Subject", id="subject-input")
            yield TextArea("", id="body-input")
            yield Label("", id="error-msg")
            with Horizontal(id="button-bar"):
                yield Button("Send Reply", id="send-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn")

    def action_cancel(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            self._send_reply()
        elif event.button.id == "cancel-btn":
            self.dismiss()

    @work(thread=True)
    def _send_reply(self) -> None:
        subject = self.query_one("#subject-input", Input).value
        body = self.query_one("#body-input", TextArea).text
        recipient = self._mail.sender

        self.app.call_from_thread(self._set_sending, True)
        try:
            smtp = SMTPClient(self._config)
            smtp.send_bulk([recipient], subject, body)
            self.app.call_from_thread(self.dismiss)
        except Exception as exc:
            self.app.call_from_thread(self._show_error, str(exc))
            self.app.call_from_thread(self._set_sending, False)

    def _set_sending(self, sending: bool) -> None:
        btn = self.query_one("#send-btn", Button)
        btn.disabled = sending
        btn.label = "Sending…" if sending else "Send Reply"

    def _show_error(self, msg: str) -> None:
        self.query_one("#error-msg", Label).update(f"Error: {msg}")
