"""Tests for scripts/lib/forward_pointer.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import forward_pointer as fp  # noqa: E402

FIXTURE_TODOS = Path(__file__).resolve().parent / "fixtures" / "chat-with-todos.jsonl"


class TestForwardPointer(unittest.TestCase):
    def test_pattern_next_step_en(self) -> None:
        extract = {
            "user_messages": [],
            "source_path": "",
        }
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "chat.jsonl"
            jsonl.write_text(
                json.dumps(
                    {
                        "role": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Summary.\n\nNext step: run flutter test on device",
                                }
                            ]
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            extract["source_path"] = str(jsonl)
            hit = fp.extract_forward_pointer(extract)
            self.assertIsNotNone(hit)
            self.assertIn("flutter test", hit.lower())

    def test_user_commitment_beats_assistant_action_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "chat.jsonl"
            lines = [
                {
                    "role": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": "Confirming Python version limitations for the build.",
                            }
                        ]
                    },
                },
                {
                    "role": "user",
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": "<user_query>okay, then run ./scripts/resync-all.sh on prod</user_query>",
                            }
                        ]
                    },
                },
            ]
            jsonl.write_text(
                "\n".join(json.dumps(row) for row in lines) + "\n",
                encoding="utf-8",
            )
            extract = {"user_messages": [], "source_path": str(jsonl)}
            hit = fp.extract_forward_pointer(extract)
            self.assertIsNotNone(hit)
            self.assertIn("resync-all", hit)

    def test_user_commitment_ru(self) -> None:
        msg = (
            "\u043e\u043a\u0435\u0439, \u0442\u043e\u0433\u0434\u0430 "
            "\u0434\u0435\u043b\u0430\u0435\u043c \u043f\u043e\u043b\u043d\u044b\u0439 "
            "\u0440\u0435\u0441\u0438\u043d\u043a \u0434\u0438\u0441\u0442\u0438\u043b\u043b\u043e\u0432 "
            "\u0438 \u043f\u043e\u0439\u043d\u0442\u0435\u0440\u043e\u0432"
        )
        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "chat.jsonl"
            jsonl.write_text(
                json.dumps(
                    {
                        "role": "user",
                        "message": {"content": [{"type": "text", "text": msg}]},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            extract = {"user_messages": [], "source_path": str(jsonl)}
            hit = fp.extract_forward_pointer(extract)
            self.assertIsNotNone(hit)
            self.assertIn("\u0440\u0435\u0441\u0438\u043d\u043a", hit)

    def test_pointer_confidence_tiers(self) -> None:
        extract = {
            "user_messages": ["okay then deploy the security patch to prod tonight"],
            "source_path": "/nonexistent/chat.jsonl",
        }
        result = fp.extract_forward_pointer_result(extract)
        self.assertIsNotNone(result.text)
        self.assertGreaterEqual(result.confidence, 0.8)
        self.assertEqual(result.source, "user_commitment")

    def test_todo_state_beats_assistant_pattern(self) -> None:
        extract = {"user_messages": [], "source_path": str(FIXTURE_TODOS)}
        result = fp.extract_forward_pointer_result(extract)
        self.assertIsNotNone(result.text)
        self.assertEqual(result.source, "todo_state")
        self.assertGreaterEqual(result.confidence, 0.85)
        self.assertIn("device QA", result.text)

    def test_user_fallback_with_action_hint(self) -> None:
        extract = {
            "user_messages": [
                "please run ./scripts/run-device.sh and record a 3 minute session"
            ],
            "source_path": "/nonexistent/chat.jsonl",
        }
        hit = fp.extract_forward_pointer(extract)
        self.assertIsNotNone(hit)
        self.assertIn("run-device", hit)


if __name__ == "__main__":
    unittest.main()
