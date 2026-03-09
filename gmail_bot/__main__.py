"""gmail_bot CLI.

Usage:
    python -m gmail_bot send --to addr --subject "..." --body "..."
    python -m gmail_bot reply --subject "query" --body "..." [--to addr] [--cc addr]
    python -m gmail_bot reply --subject "query" --dry-run
"""

import argparse
import sys

from .config import load_config
from .imap import search_by_subject
from .smtp import send_mail, reply_thread


def cmd_send(args):
    cfg = load_config(args.config)
    body = _read_body(args)
    send_mail(cfg, to=args.to, subject=args.subject, body=body, cc=args.cc)


def cmd_reply(args):
    cfg = load_config(args.config)

    results = search_by_subject(cfg, args.subject)
    if not results:
        print(f"No message found matching: {args.subject}", file=sys.stderr)
        sys.exit(1)

    original = results[0]
    print(f"Found: [{original.date}] {original.subject}")
    print(f"  From: {original.sender}")
    print(f"  Message-ID: {original.message_id}")

    if args.dry_run:
        print(f"  References: {original.references}")
        return

    body = _read_body(args)
    reply_thread(cfg, original, body, to=args.to, cc=args.cc)


def _read_body(args) -> str:
    if args.body_file:
        with open(args.body_file) as f:
            return f.read()
    if args.body:
        return args.body
    # Read from stdin if neither provided
    if not sys.stdin.isatty():
        return sys.stdin.read()
    print("Error: provide --body, --body-file, or pipe stdin", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(prog="gmail_bot", description="Gmail CLI bot")
    parser.add_argument("--config", default="gmail.yaml", help="Path to gmail.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    # send
    p_send = sub.add_parser("send", help="Send a new email")
    p_send.add_argument("--to", required=True, action="append", help="Recipient (repeatable)")
    p_send.add_argument("--cc", action="append", help="CC (repeatable)")
    p_send.add_argument("--subject", required=True)
    p_send.add_argument("--body", help="Body text")
    p_send.add_argument("--body-file", help="Read body from file")
    p_send.set_defaults(func=cmd_send)

    # reply
    p_reply = sub.add_parser("reply", help="Reply to a thread")
    p_reply.add_argument("--subject", required=True, help="Subject substring to find thread")
    p_reply.add_argument("--to", action="append", help="Override recipient (repeatable)")
    p_reply.add_argument("--cc", action="append", help="CC (repeatable)")
    p_reply.add_argument("--body", help="Reply body text")
    p_reply.add_argument("--body-file", help="Read body from file")
    p_reply.add_argument("--dry-run", action="store_true", help="Find thread only, don't send")
    p_reply.set_defaults(func=cmd_reply)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
