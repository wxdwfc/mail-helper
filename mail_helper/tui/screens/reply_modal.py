from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, TextArea
from textual.containers import Horizontal, Vertical

from ...ai_analyzer import suggest_reply
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
            yield Input(placeholder="AI instruction (e.g. decline politely, reply in Chinese…)", id="ai-instruction")
            yield Label("", id="error-msg")
            with Horizontal(id="button-bar"):
                yield Button("Send Reply", id="send-btn", variant="primary")
                yield Button("AI Suggest", id="ai-suggest-btn", variant="success")
                yield Button("Cancel", id="cancel-btn")

    def action_cancel(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            self._send_reply()
        elif event.button.id == "ai-suggest-btn":
            self._ai_suggest()
        elif event.button.id == "cancel-btn":
            self.dismiss()

    @work(thread=True)
    def _ai_suggest(self) -> None:
        instruction = self.query_one("#ai-instruction", Input).value.strip()
        self.app.call_from_thread(self._set_suggesting, True)
        try:
            draft = suggest_reply(self._mail, self._config, instruction=instruction)
            self.app.call_from_thread(self._fill_draft, draft)
        except Exception as exc:
            self.app.call_from_thread(self._show_error, str(exc))
        finally:
            self.app.call_from_thread(self._set_suggesting, False)

    def _set_suggesting(self, active: bool) -> None:
        btn = self.query_one("#ai-suggest-btn", Button)
        btn.disabled = active
        btn.label = "Thinking…" if active else "AI Suggest"

    def _fill_draft(self, text: str) -> None:
        self.query_one("#body-input", TextArea).load_text(text)

    @work(thread=True)
    def _send_reply(self) -> None:
        subject = self.query_one("#subject-input", Input).value
        body = self.query_one("#body-input", TextArea).text

        self.app.call_from_thread(self._set_sending, True)
        try:
            smtp = SMTPClient(self._config)
            smtp.send_reply(self._mail, subject, body)
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
