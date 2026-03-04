import json
from collections.abc import Callable
from dataclasses import dataclass

from openai import OpenAI

from .config import AppConfig
from .mail_backend import MailMessage

IMPORTANCE_ORDER = {"high": 0, "medium": 1, "low": 2}

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


def analyze_mails(
    mails: list[MailMessage],
    config: AppConfig,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[AnalysisResult]:
    client = OpenAI(api_key=config.ai_api_key, base_url=config.ai_api_base)
    total = len(mails)
    results: list[AnalysisResult] = []

    for i, mail in enumerate(mails):
        try:
            summary = [{"uid": mail.uid, "subject": mail.subject, "body_preview": mail.body[:500]}]

            response = client.chat.completions.create(
                model=config.ai_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(summary, ensure_ascii=False)},
                ],
                temperature=0.2,
            )

            raw = response.choices[0].message.content or "[]"
            data = json.loads(raw)

            for item in data:
                results.append(
                    AnalysisResult(
                        uid=str(item["uid"]),
                        importance=item.get("importance", "low"),
                        reason=item.get("reason", ""),
                        action=item.get("action", ""),
                    )
                )
        except Exception:
            pass  # skip this email, continue with the rest

        if on_progress:
            on_progress(i + 1, total)

    results.sort(key=lambda r: IMPORTANCE_ORDER.get(r.importance, 2))
    return results
