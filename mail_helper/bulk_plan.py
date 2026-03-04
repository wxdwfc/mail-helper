from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any
import tomllib


_ALLOWED_TOP_LEVEL_KEYS = {"templates", "emails"}
_ALLOWED_TEMPLATE_KEYS = {"subject", "body", "body_file"}
_ALLOWED_EMAIL_KEYS = {"to", "template", "vars"}
_ALLOWED_VAR_TYPES = (str, int, float, bool)


class BulkPlanError(ValueError):
    """Raised when a bulk-send TOML plan is invalid."""


@dataclass
class MailTemplate:
    id: str
    subject_template: str
    body_template: str | None = None
    body_file: str | None = None


@dataclass
class PlannedEmail:
    to: str
    template_id: str
    vars: dict[str, str]


@dataclass
class RenderedEmail:
    to: str
    subject: str
    body: str
    template_id: str


@dataclass
class BulkPlan:
    templates: dict[str, MailTemplate]
    emails: list[PlannedEmail]


def load_bulk_plan(path: str) -> BulkPlan:
    plan_path = Path(path)
    if not plan_path.exists():
        raise BulkPlanError(f"Plan file not found: {plan_path}")

    try:
        raw = plan_path.read_bytes()
    except OSError as exc:
        raise BulkPlanError(f"Failed to read plan file: {exc}") from exc

    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise BulkPlanError(f"Plan file must be UTF-8 text: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise BulkPlanError(f"Invalid TOML: {exc}") from exc

    if not isinstance(data, dict):
        raise BulkPlanError("Top-level TOML content must be a table.")

    unknown_top_level = sorted(set(data) - _ALLOWED_TOP_LEVEL_KEYS)
    if unknown_top_level:
        raise BulkPlanError(f"Unknown top-level key(s): {', '.join(unknown_top_level)}")

    templates_raw = data.get("templates")
    if not isinstance(templates_raw, dict) or not templates_raw:
        raise BulkPlanError("`templates` must be a non-empty table.")

    templates: dict[str, MailTemplate] = {}
    for template_id, template_raw in templates_raw.items():
        templates[template_id] = _parse_template(template_id, template_raw)

    emails_raw = data.get("emails")
    if not isinstance(emails_raw, list) or not emails_raw:
        raise BulkPlanError("`emails` must be a non-empty array of tables.")

    emails = [_parse_email(i, email_raw) for i, email_raw in enumerate(emails_raw, start=1)]
    return BulkPlan(templates=templates, emails=emails)


def render_bulk_plan(plan: BulkPlan, base_dir: Path) -> list[RenderedEmail]:
    rendered: list[RenderedEmail] = []

    for idx, item in enumerate(plan.emails, start=1):
        template = plan.templates.get(item.template_id)
        if template is None:
            raise BulkPlanError(
                f"emails[{idx}] references unknown template: {item.template_id!r}"
            )

        subject = _render_template(
            template.subject_template,
            item.vars,
            context=f"emails[{idx}] subject",
        )

        if template.body_template is not None:
            body_template = template.body_template
        else:
            assert template.body_file is not None
            body_path = (base_dir / template.body_file).resolve()
            try:
                body_template = body_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise BulkPlanError(
                    f"Failed to read body_file for template {template.id!r}: {exc}"
                ) from exc

        body = _render_template(
            body_template,
            item.vars,
            context=f"emails[{idx}] body",
        )

        rendered.append(
            RenderedEmail(
                to=item.to,
                subject=subject,
                body=body,
                template_id=item.template_id,
            )
        )

    return rendered


def preview_rows(rendered: list[RenderedEmail], limit: int) -> list[tuple[str, str, str]]:
    if limit < 0:
        raise BulkPlanError("preview limit must be >= 0")
    return [(r.to, r.subject, r.template_id) for r in rendered[:limit]]


def _parse_template(template_id: str, template_raw: Any) -> MailTemplate:
    if not isinstance(template_id, str) or not template_id.strip():
        raise BulkPlanError("template id must be a non-empty string")

    if not isinstance(template_raw, dict):
        raise BulkPlanError(f"templates.{template_id} must be a table")

    unknown_keys = sorted(set(template_raw) - _ALLOWED_TEMPLATE_KEYS)
    if unknown_keys:
        raise BulkPlanError(
            f"templates.{template_id} has unknown key(s): {', '.join(unknown_keys)}"
        )

    subject = template_raw.get("subject")
    if not isinstance(subject, str) or not subject.strip():
        raise BulkPlanError(f"templates.{template_id}.subject must be a non-empty string")

    has_body = "body" in template_raw
    has_body_file = "body_file" in template_raw
    if has_body == has_body_file:
        raise BulkPlanError(
            f"templates.{template_id} must define exactly one of `body` or `body_file`"
        )

    body: str | None = None
    body_file: str | None = None

    if has_body:
        body_val = template_raw["body"]
        if not isinstance(body_val, str):
            raise BulkPlanError(f"templates.{template_id}.body must be a string")
        body = body_val
        _extract_placeholder_fields(body, context=f"templates.{template_id}.body")

    if has_body_file:
        body_file_val = template_raw["body_file"]
        if not isinstance(body_file_val, str) or not body_file_val.strip():
            raise BulkPlanError(f"templates.{template_id}.body_file must be a non-empty string")
        body_file = body_file_val

    _extract_placeholder_fields(subject, context=f"templates.{template_id}.subject")
    return MailTemplate(
        id=template_id,
        subject_template=subject,
        body_template=body,
        body_file=body_file,
    )


def _parse_email(index: int, email_raw: Any) -> PlannedEmail:
    if not isinstance(email_raw, dict):
        raise BulkPlanError(f"emails[{index}] must be a table")

    unknown_keys = sorted(set(email_raw) - _ALLOWED_EMAIL_KEYS)
    if unknown_keys:
        raise BulkPlanError(f"emails[{index}] has unknown key(s): {', '.join(unknown_keys)}")

    to = email_raw.get("to")
    if not isinstance(to, str) or not to.strip():
        raise BulkPlanError(f"emails[{index}].to must be a non-empty string")

    template_id = email_raw.get("template")
    if not isinstance(template_id, str) or not template_id.strip():
        raise BulkPlanError(f"emails[{index}].template must be a non-empty string")

    vars_raw = email_raw.get("vars")
    if not isinstance(vars_raw, dict):
        raise BulkPlanError(f"emails[{index}].vars must be an inline table")

    rendered_vars: dict[str, str] = {}
    for key, value in vars_raw.items():
        if not isinstance(key, str) or not key.isidentifier():
            raise BulkPlanError(
                f"emails[{index}].vars key {key!r} must be a valid identifier"
            )
        if not isinstance(value, _ALLOWED_VAR_TYPES):
            raise BulkPlanError(
                f"emails[{index}].vars.{key} must be scalar (str/int/float/bool)"
            )
        rendered_vars[key] = str(value)

    return PlannedEmail(to=to.strip(), template_id=template_id.strip(), vars=rendered_vars)


def _extract_placeholder_fields(template: str, context: str) -> set[str]:
    formatter = Formatter()
    fields: set[str] = set()
    try:
        parsed = list(formatter.parse(template))
    except ValueError as exc:
        raise BulkPlanError(f"{context} has invalid placeholder syntax: {exc}") from exc

    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue

        if field_name == "":
            raise BulkPlanError(f"{context} cannot use positional placeholders like {{}}")
        if conversion:
            raise BulkPlanError(f"{context} cannot use conversion flags in placeholders")
        if format_spec:
            raise BulkPlanError(f"{context} cannot use format specifiers in placeholders")
        if not field_name.isidentifier():
            raise BulkPlanError(
                f"{context} placeholder {field_name!r} must be a simple identifier"
            )

        fields.add(field_name)

    return fields


def _render_template(template: str, vars_map: dict[str, str], context: str) -> str:
    fields = _extract_placeholder_fields(template, context=context)
    missing = sorted(field for field in fields if field not in vars_map)
    if missing:
        raise BulkPlanError(
            f"{context} missing variable(s): {', '.join(missing)}"
        )

    try:
        return template.format_map(vars_map)
    except Exception as exc:
        raise BulkPlanError(f"{context} render failed: {exc}") from exc
