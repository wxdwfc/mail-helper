from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from re import Pattern
from string import Formatter
from typing import Any
import re
import tomllib

from .bulk_plan import RenderedEmail
from .mail_backend import MailMessage


_ALLOWED_TOP_LEVEL_KEYS = {"trigger", "message", "recipients"}
_ALLOWED_TRIGGER_KEYS = {
    "sender_contains",
    "sender_regex",
    "subject_contains",
    "subject_regex",
    "body_contains",
    "body_regex",
}
_ALLOWED_MESSAGE_KEYS = {"subject", "body", "body_file"}
_ALLOWED_RECIPIENT_KEYS = {"to", "vars"}
_ALLOWED_VAR_TYPES = (str, int, float, bool)


class CFPTriggerError(ValueError):
    """Raised when a CFP trigger plan is invalid."""


@dataclass
class TriggerRule:
    sender_contains: str | None = None
    sender_regex: str | None = None
    subject_contains: str | None = None
    subject_regex: str | None = None
    body_contains: str | None = None
    body_regex: str | None = None


@dataclass
class MessageTemplate:
    subject_template: str
    body_template: str | None = None
    body_file: str | None = None


@dataclass
class PlannedRecipient:
    to: str
    vars: dict[str, str]


@dataclass
class CFPPlan:
    trigger: TriggerRule
    message: MessageTemplate
    recipients: list[PlannedRecipient]


@dataclass
class TriggerMatch:
    mail: MailMessage
    vars: dict[str, str]


def load_cfp_plan(path: str) -> CFPPlan:
    plan_path = Path(path)
    if not plan_path.exists():
        raise CFPTriggerError(f"Plan file not found: {plan_path}")

    try:
        raw = plan_path.read_bytes()
    except OSError as exc:
        raise CFPTriggerError(f"Failed to read plan file: {exc}") from exc

    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise CFPTriggerError(f"Plan file must be UTF-8 text: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise CFPTriggerError(f"Invalid TOML: {exc}") from exc

    if not isinstance(data, dict):
        raise CFPTriggerError("Top-level TOML content must be a table.")

    unknown_top_level = sorted(set(data) - _ALLOWED_TOP_LEVEL_KEYS)
    if unknown_top_level:
        raise CFPTriggerError(f"Unknown top-level key(s): {', '.join(unknown_top_level)}")

    trigger_raw = data.get("trigger")
    if not isinstance(trigger_raw, dict):
        raise CFPTriggerError("`trigger` must be a table.")
    trigger = _parse_trigger(trigger_raw)

    message_raw = data.get("message")
    if not isinstance(message_raw, dict):
        raise CFPTriggerError("`message` must be a table.")
    message = _parse_message(message_raw)

    recipients_raw = data.get("recipients")
    if not isinstance(recipients_raw, list) or not recipients_raw:
        raise CFPTriggerError("`recipients` must be a non-empty array of tables.")
    recipients = [
        _parse_recipient(index, recipient_raw)
        for index, recipient_raw in enumerate(recipients_raw, start=1)
    ]

    return CFPPlan(trigger=trigger, message=message, recipients=recipients)


def find_trigger_mail(mails: list[MailMessage], trigger: TriggerRule) -> TriggerMatch | None:
    compiled = _compile_rule(trigger)
    for mail in mails:
        vars_map = _match_mail(mail, trigger, compiled)
        if vars_map is not None:
            return TriggerMatch(mail=mail, vars=vars_map)
    return None


def render_cfp_plan(plan: CFPPlan, match: TriggerMatch, base_dir: Path) -> list[RenderedEmail]:
    subject_template = plan.message.subject_template
    body_template = _load_body_template(plan.message, base_dir)
    _extract_placeholder_fields(subject_template, context="message.subject")
    _extract_placeholder_fields(body_template, context="message.body")

    rendered: list[RenderedEmail] = []
    for index, recipient in enumerate(plan.recipients, start=1):
        vars_map = _merge_vars(match.vars, recipient.vars, index=index)
        subject = _render_template(subject_template, vars_map, context=f"recipients[{index}] subject")
        body = _render_template(body_template, vars_map, context=f"recipients[{index}] body")
        rendered.append(
            RenderedEmail(
                to=recipient.to,
                subject=subject,
                body=body,
                template_id="cfp-trigger",
            )
        )
    return rendered


def _parse_trigger(trigger_raw: dict[str, Any]) -> TriggerRule:
    unknown_keys = sorted(set(trigger_raw) - _ALLOWED_TRIGGER_KEYS)
    if unknown_keys:
        raise CFPTriggerError(f"`trigger` has unknown key(s): {', '.join(unknown_keys)}")

    rule = TriggerRule(
        sender_contains=_optional_string(trigger_raw, "sender_contains"),
        sender_regex=_optional_string(trigger_raw, "sender_regex"),
        subject_contains=_optional_string(trigger_raw, "subject_contains"),
        subject_regex=_optional_string(trigger_raw, "subject_regex"),
        body_contains=_optional_string(trigger_raw, "body_contains"),
        body_regex=_optional_string(trigger_raw, "body_regex"),
    )

    if not any(
        (
            rule.sender_contains,
            rule.sender_regex,
            rule.subject_contains,
            rule.subject_regex,
            rule.body_contains,
            rule.body_regex,
        )
    ):
        raise CFPTriggerError("`trigger` must define at least one match condition.")

    for key in ("sender_regex", "subject_regex", "body_regex"):
        pattern = getattr(rule, key)
        if pattern is None:
            continue
        try:
            re.compile(pattern, flags=re.IGNORECASE)
        except re.error as exc:
            raise CFPTriggerError(f"`trigger.{key}` is not a valid regex: {exc}") from exc

    return rule


def _parse_message(message_raw: dict[str, Any]) -> MessageTemplate:
    unknown_keys = sorted(set(message_raw) - _ALLOWED_MESSAGE_KEYS)
    if unknown_keys:
        raise CFPTriggerError(f"`message` has unknown key(s): {', '.join(unknown_keys)}")

    subject = message_raw.get("subject")
    if not isinstance(subject, str) or not subject.strip():
        raise CFPTriggerError("`message.subject` must be a non-empty string.")

    has_body = "body" in message_raw
    has_body_file = "body_file" in message_raw
    if has_body == has_body_file:
        raise CFPTriggerError("`message` must define exactly one of `body` or `body_file`.")

    body: str | None = None
    body_file: str | None = None
    if has_body:
        body_raw = message_raw["body"]
        if not isinstance(body_raw, str):
            raise CFPTriggerError("`message.body` must be a string.")
        body = body_raw
    if has_body_file:
        body_file_raw = message_raw["body_file"]
        if not isinstance(body_file_raw, str) or not body_file_raw.strip():
            raise CFPTriggerError("`message.body_file` must be a non-empty string.")
        body_file = body_file_raw

    return MessageTemplate(subject_template=subject, body_template=body, body_file=body_file)


def _parse_recipient(index: int, recipient_raw: Any) -> PlannedRecipient:
    if not isinstance(recipient_raw, dict):
        raise CFPTriggerError(f"recipients[{index}] must be a table")

    unknown_keys = sorted(set(recipient_raw) - _ALLOWED_RECIPIENT_KEYS)
    if unknown_keys:
        raise CFPTriggerError(
            f"recipients[{index}] has unknown key(s): {', '.join(unknown_keys)}"
        )

    to = recipient_raw.get("to")
    if not isinstance(to, str) or not to.strip():
        raise CFPTriggerError(f"recipients[{index}].to must be a non-empty string")

    vars_raw = recipient_raw.get("vars", {})
    if not isinstance(vars_raw, dict):
        raise CFPTriggerError(f"recipients[{index}].vars must be an inline table")

    rendered_vars: dict[str, str] = {}
    for key, value in vars_raw.items():
        if not isinstance(key, str) or not key.isidentifier():
            raise CFPTriggerError(
                f"recipients[{index}].vars key {key!r} must be a valid identifier"
            )
        if not isinstance(value, _ALLOWED_VAR_TYPES):
            raise CFPTriggerError(
                f"recipients[{index}].vars.{key} must be scalar (str/int/float/bool)"
            )
        rendered_vars[key] = str(value)

    return PlannedRecipient(to=to.strip(), vars=rendered_vars)


def _compile_rule(trigger: TriggerRule) -> dict[str, Pattern[str]]:
    compiled: dict[str, Pattern[str]] = {}
    for key in ("sender_regex", "subject_regex", "body_regex"):
        pattern = getattr(trigger, key)
        if pattern:
            compiled[key] = re.compile(pattern, flags=re.IGNORECASE)
    return compiled


def _match_mail(
    mail: MailMessage,
    trigger: TriggerRule,
    compiled: dict[str, Pattern[str]],
) -> dict[str, str] | None:
    groups: dict[str, str] = {
        "trigger_uid": mail.uid,
        "trigger_subject": mail.subject,
        "trigger_sender": mail.sender,
        "trigger_date": mail.date,
        "trigger_body": mail.body,
    }

    text_fields = {
        "sender": mail.sender,
        "subject": mail.subject,
        "body": mail.body,
    }

    for field in ("sender", "subject", "body"):
        contains = getattr(trigger, f"{field}_contains")
        if contains and contains.lower() not in text_fields[field].lower():
            return None

        regex = getattr(trigger, f"{field}_regex")
        if regex:
            match = compiled[f"{field}_regex"].search(text_fields[field])
            if match is None:
                return None
            for key, value in match.groupdict().items():
                if value is None:
                    continue
                _store_group(groups, key, value)

    return groups


def _store_group(groups: dict[str, str], key: str, value: str) -> None:
    existing = groups.get(key)
    if existing is None:
        groups[key] = value
        return
    if existing != value:
        raise CFPTriggerError(
            f"Named regex group {key!r} produced conflicting values: {existing!r} vs {value!r}"
        )


def _load_body_template(message: MessageTemplate, base_dir: Path) -> str:
    if message.body_template is not None:
        return message.body_template

    assert message.body_file is not None
    body_path = (base_dir / message.body_file).resolve()
    try:
        return body_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CFPTriggerError(f"Failed to read body_file {message.body_file!r}: {exc}") from exc


def _merge_vars(trigger_vars: dict[str, str], recipient_vars: dict[str, str], index: int) -> dict[str, str]:
    merged = dict(trigger_vars)
    for key, value in recipient_vars.items():
        if key in merged:
            raise CFPTriggerError(
                f"recipients[{index}].vars.{key} conflicts with reserved trigger variable {key!r}"
            )
        merged[key] = value
    return merged


def _optional_string(raw: dict[str, Any], key: str) -> str | None:
    if key not in raw:
        return None
    value = raw[key]
    if not isinstance(value, str) or not value.strip():
        raise CFPTriggerError(f"`trigger.{key}` must be a non-empty string.")
    return value


def _extract_placeholder_fields(template: str, context: str) -> set[str]:
    formatter = Formatter()
    fields: set[str] = set()
    try:
        parsed = list(formatter.parse(template))
    except ValueError as exc:
        raise CFPTriggerError(f"{context} has invalid placeholder syntax: {exc}") from exc

    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if field_name == "":
            raise CFPTriggerError(f"{context} cannot use positional placeholders like {{}}")
        if conversion:
            raise CFPTriggerError(f"{context} cannot use conversion flags in placeholders")
        if format_spec:
            raise CFPTriggerError(f"{context} cannot use format specifiers in placeholders")
        if not field_name.isidentifier():
            raise CFPTriggerError(f"{context} placeholder {field_name!r} must be a simple identifier")
        fields.add(field_name)

    return fields


def _render_template(template: str, vars_map: dict[str, str], context: str) -> str:
    fields = _extract_placeholder_fields(template, context=context)
    missing = sorted(field for field in fields if field not in vars_map)
    if missing:
        raise CFPTriggerError(f"{context} missing variable(s): {', '.join(missing)}")

    try:
        return template.format_map(vars_map)
    except Exception as exc:
        raise CFPTriggerError(f"{context} render failed: {exc}") from exc
