# Mail Helper

A Python terminal mail client with a Textual TUI and a Claude Code `/mail` slash command.

## Features

- **Inbox tab** — fetch and browse unread emails via IMAP
- **Search tab** — keyword search across subjects and body text
- **Compose tab** — send bulk emails via SMTP (manual or TOML plan)
- **TOML bulk-send** — template + variables + dry-run preview before actual sending
- **Trigger CFP workflow** — detect a matching incoming mail, then send a templated batch
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

# Use a custom rules file
python -m mail_helper.cli analyze --rules ~/my-rules.md

# TOML-driven bulk send (dry-run preview only)
python -m mail_helper.cli bulk-send --plan bulk_mail.example.toml

# Enter send mode after preview/validation, then confirm interactively
python -m mail_helper.cli bulk-send --plan bulk_mail.example.toml --yes

# Scan recent mail, including already-read mail, for a trigger
python -m mail_helper.cli trigger-cfp --plan cfp_trigger.example.toml

# Limit scanning to unread mail only
python -m mail_helper.cli trigger-cfp --plan cfp_trigger.example.toml --scope unread

# Enter send mode, then confirm before sending
python -m mail_helper.cli trigger-cfp --plan cfp_trigger.example.toml --yes
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
For personal/runtime plans, prefer a filename like `bulk_mail.local.toml`; `*.local.toml` is gitignored.

### Trigger CFP Plan Format

`trigger-cfp` accepts a TOML file with three sections:

- `trigger`: how to identify the incoming mail
- `message`: the outgoing subject/body template
- `recipients`: who should receive the rendered mail

```toml
[trigger]
sender_contains = "Rong Chen"
subject_regex = '^Weekly report (?P<week_start>\d{4}-\d{1,2}-\d{1,2}) ~ (?P<week_end>\d{1,2}-\d{1,2})$'
body_contains = "Call for report"

[message]
subject = "[CFP] Weekly call after report {week_start} ~ {week_end}"
body_file = "templates/cfp_call.txt"

[[recipients]]
to = "alice@example.com"
vars = { name = "Alice", group = "IPADS DS" }
```

Rules:
- At least one trigger condition is required.
- `*_contains` checks are case-insensitive substring matches.
- `*_regex` checks are case-insensitive Python regexes.
- Named regex groups become template variables, such as `week_start` and `week_end`.
- Built-in trigger variables are always available: `trigger_uid`, `trigger_subject`, `trigger_sender`, `trigger_date`, `trigger_body`.
- `message` must define exactly one of `body` or `body_file`.
- `body_file` is resolved relative to the TOML file directory.
- Default mode is a dry run. Use `--yes` to enter send mode, then confirm interactively before SMTP delivery starts.

Use `cfp_trigger.example.toml` and `templates/cfp_call.txt` as a starting point.
For personal/runtime plans, prefer a filename like `cfp_trigger.local.toml`; `*.local.toml` is gitignored.

### AI filtering rules (`rule.md`)

Drop a `rule.md` in the working directory to inject personal prioritization rules into the AI prompt. Both CLI and TUI pick it up automatically — no config change needed.

```bash
cp rule.md.example rule.md
# Edit to match your priorities, then analyze as usual
```

If `rule.md` is absent the analyzer falls back to its built-in behavior. See `rule.md.example` for the format.

### Claude Code `/mail` skill

From within a Claude Code session in this directory, run `/mail` to use the AI-assisted email workflows.

## gmail_bot

A standalone Gmail CLI tool for sending emails and replying to threads. Uses `gmail.yaml` for credentials (Gmail App Password).

### Setup

```bash
# Create gmail.yaml with your Gmail credentials
cat > gmail.yaml <<EOF
acct: you@gmail.com
pwd: your-app-password
EOF
```

To get an App Password: Google Account → Security → 2-Step Verification → App passwords → Generate.

### Usage

```bash
# Send a new email
python -m gmail_bot send --to someone@example.com --subject "Hello" --body "Hi there"

# Reply to a thread (finds latest match by subject)
python -m gmail_bot reply --subject "Weekly report 2026-03-02" \
  --body "My report..." --to rongchen@sjtu.edu.cn

# Reply with CC
python -m gmail_bot reply --subject "Weekly report 2026-03-02" \
  --body "My report..." --cc group@example.com

# Dry-run: find the thread without sending
python -m gmail_bot reply --subject "Weekly report 2026-03-02" --dry-run

# Body from file or stdin
python -m gmail_bot reply --subject "Weekly report" --body-file report.txt
echo "my report" | python -m gmail_bot reply --subject "Weekly report"
```

## Project Structure

```
mail-helper/
├── main.py                        # TUI entry point
├── config.yaml.example            # Config template
├── bulk_mail.example.toml         # Example TOML bulk-send plan
├── cfp_trigger.example.toml       # Example trigger-to-CFP plan
├── templates/                     # Example body templates
├── requirements.txt
├── .claude/commands/mail.md       # /mail slash command
├── gmail_bot/                     # Standalone Gmail CLI
│   ├── __main__.py                # CLI: send + reply commands
│   ├── config.py                  # GmailConfig from gmail.yaml
│   ├── imap.py                    # IMAP search + message parsing
│   └── smtp.py                    # send_mail() + reply_thread()
└── mail_helper/
    ├── config.py                  # AppConfig + load_config()
    ├── mail_backend.py            # IMAPClient + SMTPClient
    ├── bulk_plan.py               # TOML plan parsing + rendering
    ├── cfp_trigger.py             # Trigger matching + CFP rendering
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
