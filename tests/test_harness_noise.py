"""Harness-authored turns and provider tokens must never reach the hub.

Claude Code puts compaction recaps, skill preambles and quota notices into user
turns. They read like the user spoke, but carry no intent — left alone they crowd
out real decisions, which are capped per project.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.secrets_guard import redact_secrets  # noqa: E402
from lib.system_blocks import strip_system_blocks  # noqa: E402
from lib.transcript_cursor import is_redacted_or_noise  # noqa: E402


class TestHarnessProseFiltered(unittest.TestCase):
    def test_compaction_recap_dropped(self) -> None:
        self.assertTrue(
            is_redacted_or_noise(
                "This session is being continued from a previous conversation that ran "
                "out of context. The summary below covers the earlier portion."
            )
        )

    def test_skill_preamble_dropped(self) -> None:
        self.assertTrue(
            is_redacted_or_noise(
                "Base directory for this skill: /private/tmp/bundled-skills/2.1/verify"
            )
        )

    def test_quota_notice_dropped(self) -> None:
        self.assertTrue(is_redacted_or_noise("You've hit your session limit · resets 12:40am"))

    def test_resume_boilerplate_dropped(self) -> None:
        self.assertTrue(is_redacted_or_noise("Continue from where you left off."))

    def test_case_insensitive(self) -> None:
        self.assertTrue(is_redacted_or_noise("CONTINUE FROM WHERE YOU LEFT OFF"))

    def test_real_user_text_survives(self) -> None:
        for text in (
            "Deploy example-app to staging with manual approval",
            "continue the refactor of the billing module",
            "base directory layout looks wrong in the docs",
        ):
            with self.subTest(text=text):
                self.assertFalse(is_redacted_or_noise(text))


class TestHarnessTagsStripped(unittest.TestCase):
    def test_local_command_blocks_removed(self) -> None:
        text = (
            "<local-command-caveat>Caveat: generated while running local commands."
            "</local-command-caveat>Add canonical URLs"
        )
        self.assertEqual(strip_system_blocks(text), "Add canonical URLs")

    def test_task_notification_removed(self) -> None:
        text = (
            "<task-notification><task-id>t-1</task-id><status>done</status>"
            "</task-notification>ship it"
        )
        self.assertEqual(strip_system_blocks(text), "ship it")

    def test_slash_command_blocks_removed(self) -> None:
        text = (
            "<command-name>/model</command-name><command-args>opus</command-args>"
            "<local-command-stdout>Set model to opus</local-command-stdout>"
        )
        self.assertEqual(strip_system_blocks(text), "")


class TestProviderTokensRedacted(unittest.TestCase):
    def test_anthropic_key(self) -> None:
        """`sk-[A-Za-z0-9]{20,}` never matched sk-ant-… because of the hyphens."""
        text, n = redact_secrets("key sk-ant-api03-AAAAbbbbCCCCddddEEEEffffGGGG here")
        self.assertEqual(n, 1)
        self.assertNotIn("sk-ant", text)

    def test_figma_pat(self) -> None:
        text, n = redact_secrets("token figd_aAAAbbbbCCCCddddEEEEffffGGGGhhhhIIII here")
        self.assertEqual(n, 1)
        self.assertNotIn("figd_", text)

    def test_previously_covered_tokens_still_match(self) -> None:
        for probe in (
            "ghp_AAAAbbbbCCCCddddEEEEffffGGGG1234",
            "sk-AAAAbbbbCCCCddddEEEEffffGGGG",
            "glpat-AAAAbbbbCCCCddddEEEE",
        ):
            with self.subTest(probe=probe[:8]):
                _text, n = redact_secrets(probe)
                self.assertGreaterEqual(n, 1)

    def test_ordinary_text_untouched(self) -> None:
        text, n = redact_secrets("figure out the sketch-to-code flow")
        self.assertEqual(n, 0)
        self.assertIn("figure out", text)


if __name__ == "__main__":
    unittest.main()
