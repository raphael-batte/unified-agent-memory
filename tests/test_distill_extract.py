"""Tests for scripts/distill-extract.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import REPO_ROOT, load_script_module

import sys

SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
from lib import transcript_cursor as tc  # noqa: E402

de = load_script_module("distill_extract", "distill-extract.py")

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "sample-chat.jsonl"
BAD_SCHEMA = REPO_ROOT / "tests" / "fixtures" / "bad-schema.jsonl"
FIXTURE_UUID = "sample-chat"


class TestDistillExtractHelpers(unittest.TestCase):
    def test_workspace_slug(self) -> None:
        self.assertEqual(
            de.workspace_slug("Users-alice-Work-example-app"),
            "example-app",
        )

    def test_normalize_user_query(self) -> None:
        raw = "<user_query>\n  hello world  \n</user_query>"
        self.assertEqual(de.normalize_user_text(raw), "hello world")

    def test_skips_redacted(self) -> None:
        self.assertTrue(de.is_redacted_or_noise("[REDACTED]"))

    def test_extract_user_messages(self) -> None:
        msgs, total, strat, _red, _adapter = de.extract_user_messages(FIXTURE, strategy="all")
        self.assertEqual(strat, "all")
        self.assertEqual(total, 3)
        self.assertEqual(len(msgs), 3)
        self.assertIn("Deploy example-app", msgs[0])
        self.assertIn("docker ssl", msgs[-1])

    def test_truncation_tail_keeps_head_and_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "many.jsonl"
            lines = []
            for i in range(50):
                lines.append(
                    json.dumps(
                        {
                            "role": "user",
                            "message": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": f"<user_query>msg {i}</user_query>",
                                    }
                                ]
                            },
                        }
                    )
                )
            path.write_text("\n".join(lines), encoding="utf-8")
            msgs, total, strat, _, _ = de.extract_user_messages(
                path, max_messages=5, strategy="tail"
            )
            self.assertEqual(strat, "tail")
            self.assertEqual(total, 50)
            self.assertEqual(len(msgs), 5)
            self.assertTrue(msgs[0].startswith("msg 0"))
            self.assertTrue(msgs[-1].startswith("msg 49"))

    def test_truncation_spread_samples_middle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "many.jsonl"
            lines = []
            for i in range(60):
                lines.append(
                    json.dumps(
                        {
                            "role": "user",
                            "message": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": f"<user_query>msg {i}</user_query>",
                                    }
                                ]
                            },
                        }
                    )
                )
            path.write_text("\n".join(lines), encoding="utf-8")
            msgs, total, strat, _, _ = de.extract_user_messages(
                path, max_messages=30, strategy="spread"
            )
            self.assertEqual(strat, "spread")
            self.assertEqual(total, 60)
            self.assertEqual(len(msgs), 30)
            self.assertTrue(msgs[0].startswith("msg 0"))
            self.assertTrue(msgs[-1].startswith("msg 59"))
            # spread samples middle evenly — exact index depends on pool size
            nums = [int(m.split()[1]) for m in msgs]
            self.assertTrue(any(15 <= n <= 45 for n in nums), nums)

    def test_auto_strategy_uses_importance(self) -> None:
        self.assertEqual(de.resolve_strategy("auto", 51), "importance")
        self.assertEqual(de.resolve_strategy("auto", 50), "importance")

    def test_keywords_hit(self) -> None:
        msgs, _, _, _, _ = de.extract_user_messages(FIXTURE, strategy="all")
        hits = de.keywords_hit(msgs)
        self.assertIn("deploy", hits)
        self.assertIn("prod", hits)
        self.assertIn("migration", hits)
        self.assertIn("docker", hits)

    def test_build_extract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ws = root / "Users-alice-Work-example-app" / "agent-transcripts" / FIXTURE_UUID
            ws.mkdir(parents=True)
            jsonl = ws / f"{FIXTURE_UUID}.jsonl"
            jsonl.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
            data = de.build_extract(jsonl, projects_root=root, strategy="all")
        self.assertEqual(data["uuid"], FIXTURE_UUID)
        self.assertEqual(data["workspace_slug"], "example-app")
        self.assertEqual(data["user_message_count"], 3)
        self.assertFalse(data["truncated"])
        self.assertGreater(len(data["keywords_hit"]), 0)


class TestDistillExtractCLI(unittest.TestCase):
    def test_main_by_path_stdout(self) -> None:
        argv = [
            "distill-extract.py",
            "--path",
            str(FIXTURE),
            "--all",
        ]
        with mock.patch.object(sys, "argv", argv):
            with mock.patch("sys.stdout") as out:
                self.assertEqual(de.main(), 0)
                written = "".join(
                    str(c.args[0]) for c in out.write.call_args_list
                )
                payload = json.loads(written)
                self.assertEqual(payload["user_message_count"], 3)

    def test_main_bad_schema_exits_one(self) -> None:
        argv = ["distill-extract.py", "--path", str(BAD_SCHEMA)]
        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(de.main(), 1)

    def test_transcript_schema_error(self) -> None:
        with self.assertRaises(tc.TranscriptSchemaError):
            tc.extract_raw_user_texts(BAD_SCHEMA)

    def test_main_missing_uuid(self) -> None:
        argv = ["distill-extract.py", "nonexistent-uuid-00000000"]
        with mock.patch.object(sys, "argv", argv):
            with mock.patch.object(de, "DEFAULT_PROJECTS_ROOT", FIXTURE.parent):
                self.assertEqual(de.main(), 1)


if __name__ == "__main__":
    unittest.main()
