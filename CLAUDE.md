# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
# TUI (requires config.yaml)
python main.py

# CLI
python -m mail_helper.cli inbox --limit 20
python -m mail_helper.cli analyze
python -m mail_helper.cli analyze --fresh   # re-fetch from IMAP before analyzing
```

## Setup

```bash
pip install -r requirements.txt
cp config.yaml.example config.yaml   # fill in IMAP/SMTP/AI credentials
```

`config.yaml` and `.mail_cache.json` are gitignored. Never commit them.

## Architecture

```
mail_helper/
├── config.py          # AppConfig dataclass + load_config("config.yaml")
├── mail_backend.py    # IMAPClient, SMTPClient, MailMessage dataclass
├── ai_analyzer.py     # OpenAI-compatible analysis → list[AnalysisResult]
├── cache.py           # save_inbox() / load_inbox() → .mail_cache.json
├── cli.py             # click CLI: inbox + analyze commands
└── tui/
    ├── app.py         # MailHelperApp(App) — bindings: r=refresh, q=quit
    ├── screens/mail_detail.py   # ModalScreen for full email view
    └── tabs/
        ├── inbox_tab.py    # DataTable + cache-first load + AI analysis button
        ├── search_tab.py   # keyword search with Unicode fallback
        └── compose_tab.py  # bulk SMTP send
```

**Data flow**: `IMAPClient` → `MailMessage` → `cache.py` (persisted to `.mail_cache.json`) → displayed in TUI or CLI. AI analysis is a separate pass via `ai_analyzer.py` using the OpenAI SDK with a configurable `base_url`.

## Textual 8.x critical patterns

- Import `work` from `textual` (not `textual.worker`): `from textual import work`
- `call_from_thread` only exists on `App`, not on `Widget`/`TabPane` — always use `self.app.call_from_thread(fn, *args)` from within `@work(thread=True)` methods
- DataTable row key retrieval: `str(event.row_key.value)`, not `.row_key` directly

## IMAP search (Unicode)

`search_keyword()` tries server-side `CHARSET UTF-8` first; if the server rejects it, falls back to fetching the last 200 emails and filtering client-side in Python.

## AI provider

`ai_analyzer.py` uses the `openai` SDK with `base_url` set from `config.yaml`. Works with any OpenAI-compatible endpoint (OpenAI, Groq, Ollama, etc.). Config fields: `ai_api_base`, `ai_api_key`, `ai_model`.

## Cache deduplication

On inbox refresh, `get_unread_uids()` fetches only the IMAP UID list; `fetch_uids()` is called only for UIDs not already in `_mail_map`. This avoids re-downloading bodies for already-cached emails.
