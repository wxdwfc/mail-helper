# Mail Helper

A Python terminal mail client with a Textual TUI and a Claude Code `/mail` slash command.

## Features

- **Inbox tab** — fetch and browse unread emails via IMAP
- **Search tab** — keyword search across subjects and body text
- **Compose tab** — send bulk emails via SMTP (manual or TOML plan)
- **TOML bulk-send** — template + variables + dry-run preview before actual sending
- **Mail detail modal** — scrollable full-email view
- **CLI** — `inbox`, `analyze`, and `bulk-send` commands for scripting and automation
- **AI prioritization** — ranks emails by importance using any OpenAI-compatible model

## Setup

```bash
pip install -r requirements.txt
cp config.yaml.example config.yaml
# Edit config.yaml with your credentials
```

### config.yaml fields

| Field | Description |
|---|---|
| `imap_host` / `imap_port` | IMAP server (e.g. `imap.gmail.com`, `993`) |
| `smtp_host` / `smtp_port` | SMTP server (e.g. `smtp.gmail.com`, `587`) |
| `smtp_use_ssl` | `true` for port 465, `false` for port 587 (STARTTLS) |
| `email` / `password` | Your email address and app password |
| `ai_api_base` | OpenAI-compatible base URL (e.g. `https://api.openai.com/v1`) |
| `ai_api_key` | API key for the AI provider |
| `ai_model` | Model name (e.g. `gpt-4o-mini`) |
| `fetch_count` | Max emails to fetch (default: 50) |

> For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833) instead of your account password.

## Usage

### TUI

```bash
python main.py
```

Keyboard shortcuts:
- `R` — refresh inbox
- `Enter` — open email detail
- `Escape` — close detail modal
- `Q` — quit

Compose tab supports two bulk-send paths:
- Manual: one subject/body for recipients entered line-by-line
- TOML plan: load plan path, preview rendered rows, then click `Send From TOML`

### CLI

```bash
# Fetch and display unread emails
python -m mail_helper.cli inbox --limit 20

# AI-prioritized analysis (uses cached emails)
python -m mail_helper.cli analyze

# Re-fetch from server before analyzing
python -m mail_helper.cli analyze --fresh

# TOML-driven bulk send (dry-run preview only)
python -m mail_helper.cli bulk-send --plan bulk_mail.example.toml

# Actually send after preview/validation
python -m mail_helper.cli bulk-send --plan bulk_mail.example.toml --yes
```

### TOML Bulk Plan Format

`bulk-send` accepts a TOML file with templates and email items.

```toml
[templates.welcome]
subject = "Hi {name}, welcome to {team}"
body_file = "templates/welcome.txt"
# body and body_file are mutually exclusive

[[emails]]
to = "alice@example.com"
template = "welcome"
vars = { name = "Alice", team = "Infra" }

[[emails]]
to = "bob@example.com"
template = "welcome"
vars = { name = "Bob", team = "Infra" }
```

Rules:
- `templates.<id>.subject` is required.
- Exactly one of `templates.<id>.body` or `templates.<id>.body_file` must be set.
- `[[emails]]` entries require `to`, `template`, and `vars`.
- Placeholder syntax is `{name}` (Python `str.format_map`).
- `body_file` is resolved relative to the TOML file directory.
- Any validation/render error blocks the entire send (no partial send starts).

Use `bulk_mail.example.toml` and `templates/welcome.txt` as a starting point.

### Claude Code `/mail` skill

From within a Claude Code session in this directory, run `/mail` to use the AI-assisted email workflows.

## Project Structure

```
mail-helper/
├── main.py                        # TUI entry point
├── config.yaml.example            # Config template
├── bulk_mail.example.toml         # Example TOML bulk-send plan
├── templates/                     # Example body templates
├── requirements.txt
├── .claude/commands/mail.md       # /mail slash command
└── mail_helper/
    ├── config.py                  # AppConfig + load_config()
    ├── mail_backend.py            # IMAPClient + SMTPClient
    ├── bulk_plan.py               # TOML plan parsing + rendering
    ├── ai_analyzer.py             # AI importance analysis
    ├── cli.py                     # Click CLI
    └── tui/
        ├── app.py                 # MailHelperApp
        ├── screens/mail_detail.py # Email detail modal
        └── tabs/
            ├── inbox_tab.py
            ├── search_tab.py
            └── compose_tab.py
```

## Requirements

- Python 3.12+
- Textual 8.x
- An IMAP/SMTP email account
- An OpenAI-compatible API key (for `analyze` command)
