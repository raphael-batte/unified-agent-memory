"""Tests for scripts/lib/pointer_feedback.py"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import minimal_hub

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.distill_metrics import read_metrics  # noqa: E402
from lib.pointer_feedback import (  # noqa: E402
    classify_session_adherence,
    log_session_start_pointer_feedback,
    token_overlap_ratio,
)


class TestPointerFeedback(unittest.TestCase):
    def test_logs_unmeasured_for_real_pointer_without_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            minimal_hub(hub, projects=0)
            project = hub / "chats" / "projects" / "app.md"
            project.parent.mkdir(parents=True, exist_ok=True)
            project.write_text(
                "## Next step\n\n- Run smoke tests on staging\n\n## Recent\n\n",
                encoding="utf-8",
            )
            rows = log_session_start_pointer_feedback(hub, {"app"})
            self.assertEqual(rows[0]["outcome"], "unmeasured")
            self.assertTrue(rows[0]["disk_hit"])
            metrics = read_metrics(hub)
            self.assertTrue(any(r.get("event") == "pointer_feedback" for r in metrics))

    def test_logs_miss_for_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            project = hub / "chats" / "projects" / "app.md"
            project.parent.mkdir(parents=True, exist_ok=True)
            project.write_text(
                "## Next step\n\n- _No forward pointer._\n\n",
                encoding="utf-8",
            )
            rows = log_session_start_pointer_feedback(hub, {"app"})
            self.assertEqual(rows[0]["outcome"], "miss")
            self.assertFalse(rows[0]["disk_hit"])

    def test_token_overlap_followed(self) -> None:
        ratio = token_overlap_ratio(
            "Run smoke tests on staging",
            ["let's run smoke tests on staging now"],
        )
        self.assertGreaterEqual(ratio, 0.35)
        outcome, score = classify_session_adherence(
            "Run smoke tests on staging",
            ["let's run smoke tests on staging now"],
            None,
        )
        self.assertEqual(outcome, "followed")
        self.assertGreaterEqual(score, 0.35)

    def test_session_adherence_resumed_blind(self) -> None:
        outcome, _ = classify_session_adherence(
            "Deploy v0.18 to production",
            ["hi"],
            None,
        )
        self.assertEqual(outcome, "resumed_blind")

    def test_followed_with_transcript_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            projects = Path(tmp) / "projects"
            chat_id = "abc12345-dead-beef-cafe-000000000001"
            ws = (
                projects
                / "Users-me-Work-App"
                / "agent-transcripts"
                / chat_id
            )
            ws.mkdir(parents=True)
            jsonl = ws / f"{chat_id}.jsonl"
            jsonl.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "role": "user",
                                "message": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "run smoke tests on staging please",
                                        }
                                    ]
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            project = hub / "chats" / "projects" / "app.md"
            project.parent.mkdir(parents=True, exist_ok=True)
            project.write_text(
                "## Next step\n\n- Run smoke tests on staging\n\n",
                encoding="utf-8",
            )
            manifest = hub / "chats" / "manifest.json"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                json.dumps(
                    {
                        "processed": [
                            {
                                "id": chat_id,
                                "distilled_to": ["projects/app.md"],
                                "distilled_at": "2026-06-08",
                                "watermark_user_count": 0,
                            }
                        ],
                        "pending": [],
                    }
                ),
                encoding="utf-8",
            )
            payload = {
                "transcript_path": str(jsonl),
                "workspace_roots": [str(projects / "Users-me-Work-App")],
            }
            rows = log_session_start_pointer_feedback(
                hub,
                {"app"},
                payload=payload,
                projects_root=projects,
            )
            self.assertEqual(rows[0]["session_outcome"], "followed")
            self.assertEqual(rows[0]["outcome"], "followed")


if __name__ == "__main__":
    unittest.main()
