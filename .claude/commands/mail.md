# /mail — AI-Assisted Email Workflows

Use this command to check and prioritize your email directly from Claude Code.

## Prerequisites

1. `config.yaml` must exist in `/Users/wxd/lab/okr-dev/mail-helper/` (copy from `config.yaml.example`)
2. Dependencies must be installed: `pip install -r requirements.txt`
3. Run commands from the project root: `cd /Users/wxd/lab/okr-dev/mail-helper`

---

## Workflow 1 — Show Unread Inbox

Run this to fetch and display unread emails:

```bash
cd /Users/wxd/lab/okr-dev/mail-helper && python -m mail_helper.cli inbox --limit 20
```

**Options:**
- `--limit N` — fetch at most N emails (default: 20)
- `--no-save` — skip saving results to `.mail_cache.json`

After running, present the results to the user and ask if they want to:
- Open a specific email (show its body)
- Analyze the inbox with AI (Workflow 2)
- Reply/compose a response

---

## Workflow 2 — AI Prioritization

Run this to analyze cached emails and rank by importance:

```bash
cd /Users/wxd/lab/okr-dev/mail-helper && python -m mail_helper.cli analyze
```

Add `--fresh` to re-fetch from the server before analyzing:

```bash
cd /Users/wxd/lab/okr-dev/mail-helper && python -m mail_helper.cli analyze --fresh
```

After running, present the prioritized list to the user. For "high" priority emails:
- Summarize what action is needed
- Offer to help draft a reply

---

## Notes

- The AI analysis uses whatever OpenAI-compatible provider is configured in `config.yaml`
- Results are cached in `.mail_cache.json` to avoid redundant IMAP fetches
- Use `python main.py` to launch the interactive TUI instead
