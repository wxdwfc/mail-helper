import json
import os
from collections.abc import Callable
from dataclasses import dataclass

from openai import OpenAI

from .config import AppConfig
from .mail_backend import MailMessage

IMPORTANCE_ORDER = {"high": 0, "medium": 1, "low": 2}

REPLY_SYSTEM_PROMPT = """\
You are a professional email assistant. Given the original email, draft a concise and polite reply.
Return ONLY the reply body text, no subject line, no markdown fences, no extra commentary.
"""

SYSTEM_PROMPT = """\
You are an email prioritization assistant. Given a list of emails in JSON format,
analyze each one and return a JSON array with one object per email.

Each object must have these fields:
- uid: the email uid (string, same as input)
- importance: "high", "medium", or "low"
- reason: one sentence explaining why
- action: one sentence suggesting what to do

Return ONLY the JSON array, no markdown fences, no extra text.
"""


@dataclass
class AnalysisResult:
    uid: str
    importance: str
    reason: str
    action: str


def _load_rules(path: str = "rule.md") -> str | None:
    """Return contents of rules file if it exists, else None."""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return None


def suggest_reply(
    mail: "MailMessage",
    config: "AppConfig",
    instruction: str = "",
    prompt_path: str = "reply_prompt.md",
) -> str:
    """Return an AI-drafted reply body for the given email."""
    client = OpenAI(api_key=config.ai_api_key, base_url=config.ai_api_base)

    system_prompt = REPLY_SYSTEM_PROMPT
    custom = _load_rules(prompt_path)
    if custom:
        system_prompt += "\n\n## User instructions\n\n" + custom

    user_content = (
        f"From: {mail.sender}\nSubject: {mail.subject}\n\n{mail.body or '(no body)'}"
    )
    if instruction:
        user_content += f"\n\n## How to reply\n{instruction}"
    response = client.chat.completions.create(
        model=config.ai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.5,
    )
    return (response.choices[0].message.content or "").strip()


def analyze_mails(
    mails: list[MailMessage],
    config: AppConfig,
    on_progress: Callable[[int, int], None] | None = None,
    on_result: Callable[["AnalysisResult", int, int], None] | None = None,
    rules_path: str = "rule.md",
) -> list[AnalysisResult]:
    client = OpenAI(api_key=config.ai_api_key, base_url=config.ai_api_base)
    total = len(mails)
    results: list[AnalysisResult] = []

    rules = _load_rules(rules_path)
    system_prompt = SYSTEM_PROMPT
    if rules:
        system_prompt += "\n\n## User-defined rules\n\n" + rules

    for i, mail in enumerate(mails):
        result: AnalysisResult | None = None
        try:
            summary = [{"uid": mail.uid, "subject": mail.subject, "body_preview": mail.body[:500]}]

            response = client.chat.completions.create(
                model=config.ai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(summary, ensure_ascii=False)},
                ],
                temperature=0.2,
            )

            raw = response.choices[0].message.content or "[]"
            data = json.loads(raw)

            for item in data:
                result = AnalysisResult(
                    uid=str(item["uid"]),
                    importance=item.get("importance", "low"),
                    reason=item.get("reason", ""),
                    action=item.get("action", ""),
                )
                results.append(result)
        except Exception:
            pass  # skip this email, continue with the rest

        if on_result and result:
            on_result(result, i + 1, total)
        if on_progress:
            on_progress(i + 1, total)

    results.sort(key=lambda r: IMPORTANCE_ORDER.get(r.importance, 2))
    return results
