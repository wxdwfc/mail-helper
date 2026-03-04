# Mail Helper

A Python terminal mail client with a Textual TUI and a Claude Code `/mail` slash command.

## Features

- **Inbox tab** — fetch and browse unread emails via IMAP
- **Search tab** — keyword search across subjects and body text
- **Compose tab** — send bulk emails via SMTP
- **Mail detail modal** — scrollable full-email view
- **CLI** — `inbox` and `analyze` commands for scripting and Claude Code integration
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

### CLI

```bash
# Fetch and display unread emails
python -m mail_helper.cli inbox --limit 20

# AI-prioritized analysis (uses cached emails)
python -m mail_helper.cli analyze

# Re-fetch from server before analyzing
python -m mail_helper.cli analyze --fresh
```

### Claude Code `/mail` skill

From within a Claude Code session in this directory, run `/mail` to use the AI-assisted email workflows.

## Project Structure

```
mail-helper/
├── main.py                        # TUI entry point
├── config.yaml.example            # Config template
├── requirements.txt
├── .claude/commands/mail.md       # /mail slash command
└── mail_helper/
    ├── config.py                  # AppConfig + load_config()
    ├── mail_backend.py            # IMAPClient + SMTPClient
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
