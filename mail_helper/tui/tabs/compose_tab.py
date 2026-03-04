from textual.app import ComposeResult
from textual.widgets import Button, Input, Label, TabPane, TextArea
from textual import work

from ...config import AppConfig
from ...mail_backend import SMTPClient


class ComposeTab(TabPane):
    DEFAULT_CSS = """
    ComposeTab {
        padding: 1;
    }
    ComposeTab Label.field-label {
        margin-top: 1;
    }
    ComposeTab TextArea {
        height: 8;
        margin-bottom: 1;
    }
    ComposeTab #body-area {
        height: 12;
    }
    ComposeTab Button {
        margin-top: 1;
    }
    ComposeTab #status {
        margin-top: 1;
        color: $text-muted;
    }
    """

    def __init__(self, config: AppConfig) -> None:
        super().__init__("Compose", id="compose")
        self._config = config

    def compose(self) -> ComposeResult:
        yield Label("Recipients (one per line):", classes="field-label")
        yield TextArea(id="recipients-area")
        yield Label("Subject:", classes="field-label")
        yield Input(placeholder="Email subject…", id="subject-input")
        yield Label("Body:", classes="field-label")
        yield TextArea(id="body-area")
        yield Button("Send", variant="primary", id="send-btn")
        yield Label("", id="status")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            recipients_raw = self.query_one("#recipients-area", TextArea).text
            subject = self.query_one("#subject-input", Input).value.strip()
            body = self.query_one("#body-area", TextArea).text

            recipients = [r.strip() for r in recipients_raw.splitlines() if r.strip()]
            if not recipients:
                self._set_status("No recipients specified.")
                return
            if not subject:
                self._set_status("Subject is empty.")
                return

            self._send_mails(recipients, subject, body)

    @work(thread=True)
    def _send_mails(self, recipients: list[str], subject: str, body: str) -> None:
        self.app.call_from_thread(self._set_status, f"Sending to {len(recipients)} recipient(s)…")
        client = SMTPClient(self._config)
        try:
            sent, failed = client.send_bulk(recipients, subject, body)
        except Exception as exc:
            self.app.call_from_thread(self._set_status, f"Error: {exc}")
            return

        parts = []
        if sent:
            parts.append(f"Sent to {len(sent)}")
        if failed:
            parts.append(f"Failed: {', '.join(failed)}")
        self.app.call_from_thread(self._set_status, " | ".join(parts) if parts else "Done.")

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Label).update(text)
