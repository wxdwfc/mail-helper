from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Input, Label, TabPane, TextArea

from ...bulk_plan import BulkPlanError, RenderedEmail, load_bulk_plan, preview_rows, render_bulk_plan
from ...config import AppConfig
from ...mail_backend import SMTPClient

_PREVIEW_MAX_ROWS = 50


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
    ComposeTab #bulk-plan-row {
        height: auto;
        margin-top: 1;
    }
    ComposeTab #bulk-plan-row Input {
        width: 1fr;
    }
    ComposeTab #bulk-plan-row Button {
        margin-left: 1;
    }
    ComposeTab #plan-preview-table {
        height: 10;
        margin-top: 1;
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
        self._rendered_from_plan: list[RenderedEmail] = []
        self._plan_path: Path | None = None

    def compose(self) -> ComposeResult:
        yield Label("Recipients (one per line):", classes="field-label")
        yield TextArea(id="recipients-area")
        yield Label("Subject:", classes="field-label")
        yield Input(placeholder="Email subject…", id="subject-input")
        yield Label("Body:", classes="field-label")
        yield TextArea(id="body-area")
        yield Button("Send", variant="primary", id="send-btn")

        yield Label("Bulk Plan TOML:", classes="field-label")
        with Horizontal(id="bulk-plan-row"):
            yield Input(placeholder="Path to bulk TOML plan…", id="plan-input")
            yield Button("Load TOML", id="load-plan-btn")
            yield Button("Send From TOML", variant="primary", id="send-plan-btn", disabled=True)

        yield DataTable(id="plan-preview-table")
        yield Label("", id="status")

    def on_mount(self) -> None:
        table = self.query_one("#plan-preview-table", DataTable)
        table.add_columns("To", "Subject", "Template")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "plan-input":
            self._load_plan_from_input()

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
            return

        if event.button.id == "load-plan-btn":
            self._load_plan_from_input()
            return

        if event.button.id == "send-plan-btn":
            if not self._rendered_from_plan:
                self._set_status("No loaded TOML plan. Load one first.")
                return
            self._send_from_plan()

    def _load_plan_from_input(self) -> None:
        raw_path = self.query_one("#plan-input", Input).value.strip()
        if not raw_path:
            self._set_status("Plan path is empty.")
            return
        self._load_plan(raw_path)

    @work(thread=True, exclusive=True)
    def _load_plan(self, raw_path: str) -> None:
        self.app.call_from_thread(self._set_status, "Loading TOML plan…")
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()

        try:
            plan = load_bulk_plan(str(path))
            rendered = render_bulk_plan(plan, base_dir=path.parent)
        except BulkPlanError as exc:
            self.app.call_from_thread(self._on_plan_load_error, str(exc))
            return
        except Exception as exc:
            self.app.call_from_thread(self._on_plan_load_error, f"Error: {exc}")
            return

        self.app.call_from_thread(self._on_plan_loaded, rendered, path)

    @work(thread=True, exclusive=True)
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

    @work(thread=True, exclusive=True)
    def _send_from_plan(self) -> None:
        rendered = list(self._rendered_from_plan)
        if not rendered:
            self.app.call_from_thread(self._set_status, "No loaded TOML plan. Load one first.")
            return

        self.app.call_from_thread(self._set_send_plan_btn, True)
        self.app.call_from_thread(
            self._set_status,
            f"Sending {len(rendered)} recipient(s) from TOML plan…",
        )

        client = SMTPClient(self._config)
        try:
            sent, failed = client.send_rendered(rendered)
        except Exception as exc:
            self.app.call_from_thread(self._set_status, f"Error: {exc}")
            self.app.call_from_thread(self._set_send_plan_btn, False)
            return

        parts = []
        if sent:
            parts.append(f"Sent to {len(sent)}")
        if failed:
            parts.append(f"Failed: {', '.join(failed)}")

        self.app.call_from_thread(self._set_status, " | ".join(parts) if parts else "Done.")
        self.app.call_from_thread(self._set_send_plan_btn, False)

    def _on_plan_load_error(self, error: str) -> None:
        self._rendered_from_plan = []
        self._plan_path = None
        self._set_send_plan_btn(True)
        self._clear_preview_table()
        self._set_status(error)

    def _on_plan_loaded(self, rendered: list[RenderedEmail], plan_path: Path) -> None:
        self._rendered_from_plan = rendered
        self._plan_path = plan_path
        self._set_send_plan_btn(not bool(rendered))
        self._populate_preview_table(rendered)

        status = f"Loaded {len(rendered)} email(s) from {plan_path}"
        if len(rendered) > _PREVIEW_MAX_ROWS:
            status += f" (showing first {_PREVIEW_MAX_ROWS})"
        self._set_status(status)

    def _set_send_plan_btn(self, disabled: bool) -> None:
        self.query_one("#send-plan-btn", Button).disabled = disabled

    def _clear_preview_table(self) -> None:
        self.query_one("#plan-preview-table", DataTable).clear()

    def _populate_preview_table(self, rendered: list[RenderedEmail]) -> None:
        table = self.query_one("#plan-preview-table", DataTable)
        table.clear()
        for to, subject, template_id in preview_rows(rendered, limit=_PREVIEW_MAX_ROWS):
            table.add_row(to[:50], subject[:70], template_id[:30])

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Label).update(text)
