from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from mail_helper.cfp_trigger import (
    CFPTriggerError,
    find_trigger_mail,
    load_cfp_plan,
    render_cfp_plan,
)
from mail_helper.mail_backend import MailMessage


class CFPTriggerTests(unittest.TestCase):
    def test_find_trigger_mail_extracts_named_groups(self) -> None:
        with TemporaryDirectory() as tmpdir:
            plan_path = Path(tmpdir) / "cfp.toml"
            plan_path.write_text(
                "\n".join(
                    [
                        "[trigger]",
                        'sender_contains = "Rong Chen"',
                        'subject_regex = "^Weekly report (?P<week_start>\\\\d{4}-\\\\d{1,2}-\\\\d{1,2}) ~ (?P<week_end>\\\\d{1,2}-\\\\d{1,2})$"',
                        'body_contains = "Call for report"',
                        "",
                        "[message]",
                        'subject = "CFP {week_start} ~ {week_end}"',
                        'body = "Hi {name}, triggered by {trigger_subject}"',
                        "",
                        "[[recipients]]",
                        'to = "alice@example.com"',
                        'vars = { name = "Alice" }',
                    ]
                ),
                encoding="utf-8",
            )

            plan = load_cfp_plan(str(plan_path))
            mails = [
                MailMessage(
                    uid="101",
                    subject="Weekly report 2026-1-19 ~ 1-25",
                    sender="Rong Chen <rc@example.com>",
                    date="Sun, 25 Jan 2026 10:00:00 +0800",
                    body="Call for report",
                )
            ]

            match = find_trigger_mail(mails, plan.trigger)

            self.assertIsNotNone(match)
            assert match is not None
            self.assertEqual(match.vars["week_start"], "2026-1-19")
            self.assertEqual(match.vars["week_end"], "1-25")

            rendered = render_cfp_plan(plan, match, base_dir=plan_path.parent)
            self.assertEqual(rendered[0].subject, "CFP 2026-1-19 ~ 1-25")
            self.assertIn("triggered by Weekly report 2026-1-19 ~ 1-25", rendered[0].body)

    def test_render_rejects_reserved_recipient_var(self) -> None:
        with TemporaryDirectory() as tmpdir:
            plan_path = Path(tmpdir) / "cfp.toml"
            plan_path.write_text(
                "\n".join(
                    [
                        "[trigger]",
                        'subject_contains = "Weekly report"',
                        "",
                        "[message]",
                        'subject = "CFP"',
                        'body = "Hi"',
                        "",
                        "[[recipients]]",
                        'to = "alice@example.com"',
                        'vars = { trigger_subject = "override" }',
                    ]
                ),
                encoding="utf-8",
            )

            plan = load_cfp_plan(str(plan_path))
            match = find_trigger_mail(
                [
                    MailMessage(
                        uid="1",
                        subject="Weekly report 2026-1-19 ~ 1-25",
                        sender="sender@example.com",
                        date="Mon, 26 Jan 2026 09:00:00 +0800",
                        body="body",
                    )
                ],
                plan.trigger,
            )

            self.assertIsNotNone(match)
            assert match is not None
            with self.assertRaises(CFPTriggerError):
                render_cfp_plan(plan, match, base_dir=plan_path.parent)

    def test_missing_placeholder_fails_render(self) -> None:
        with TemporaryDirectory() as tmpdir:
            plan_path = Path(tmpdir) / "cfp.toml"
            plan_path.write_text(
                "\n".join(
                    [
                        "[trigger]",
                        'subject_contains = "Weekly report"',
                        "",
                        "[message]",
                        'subject = "CFP {missing_var}"',
                        'body = "Hi"',
                        "",
                        "[[recipients]]",
                        'to = "alice@example.com"',
                    ]
                ),
                encoding="utf-8",
            )

            plan = load_cfp_plan(str(plan_path))
            match = find_trigger_mail(
                [
                    MailMessage(
                        uid="1",
                        subject="Weekly report 2026-1-19 ~ 1-25",
                        sender="sender@example.com",
                        date="Mon, 26 Jan 2026 09:00:00 +0800",
                        body="body",
                    )
                ],
                plan.trigger,
            )

            self.assertIsNotNone(match)
            assert match is not None
            with self.assertRaises(CFPTriggerError):
                render_cfp_plan(plan, match, base_dir=plan_path.parent)


if __name__ == "__main__":
    unittest.main()
