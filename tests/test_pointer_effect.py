"""Tests for scripts/lib/pointer_effect.py"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import boundary_hooks as bh  # noqa: E402
from lib import lang_cues as lc  # noqa: E402
from lib import pointer_effect as pe  # noqa: E402
from lib.distill_metrics import read_metrics  # noqa: E402
from lib.open_threads import collect_open_threads  # noqa: E402

TODAY = date.today().isoformat()

CURATED = {"slug": "alpha-hub", "label": "deploy", "text": "finish staging rollout for billing service", "curated": True}
AUTO = {"slug": "beta-app", "label": "ui", "text": "[auto] tweak header gradient colors", "curated": False}
OTHER = {"slug": "beta-app", "label": "docs", "text": "rewrite onboarding guide chapter", "curated": True}


def _hub(root: Path) -> Path:
    hub = root / "hub"
    projects = hub / "chats" / "projects"
    projects.mkdir(parents=True)
    (projects / "alpha-hub.md").write_text(
        f"# alpha-hub\n_Last updated: {TODAY}_\n\n## Open threads\n\n"
        f"- **[deploy]** finish staging rollout for billing service · _upd {TODAY}_\n",
        encoding="utf-8",
    )
    (projects / "beta-app.md").write_text(
        f"# beta-app\n_Last updated: {TODAY}_\n\n## Open threads\n\n"
        f"- **[ui]** [auto] tweak header gradient colors · _upd {TODAY}_\n",
        encoding="utf-8",
    )
    (hub / "transcripts").mkdir()
    return hub


def _transcript(hub: Path, chat_id: str, messages: list[str]) -> Path:
    path = hub / "transcripts" / f"{chat_id}.jsonl"
    path.write_text(
        "\n".join(json.dumps({"role": "user", "content": m}) for m in messages) + "\n",
        encoding="utf-8",
    )
    return path


class TestScoreSession(unittest.TestCase):
    def test_one_matching_thread_is_enough(self) -> None:
        """Gluing threads into one string diluted a clean match into 'ignored'."""
        row = pe.score_session(
            [OTHER, AUTO, CURATED],
            ["let's finish the staging rollout for billing", "run the service checks"],
        )
        self.assertEqual(row["outcome"], "followed")
        self.assertEqual(row["best_slug"], "alpha-hub")
        self.assertTrue(row["best_curated"])
        self.assertGreaterEqual(row["curated_score"], pe.FOLLOWED_AT)
        self.assertEqual(row["auto_score"], 0.0)
        self.assertEqual((row["threads_shown"], row["curated_shown"]), (3, 2))

    def test_auto_marker_is_not_a_curated_thread(self) -> None:
        row = pe.score_session([AUTO], ["tweak the header gradient colors please"])
        self.assertEqual(row["outcome"], "followed")
        self.assertFalse(row["best_curated"])
        self.assertGreaterEqual(row["auto_score"], pe.FOLLOWED_AT)

    def test_generic_start_scores_the_next_turns(self) -> None:
        row = pe.score_session([CURATED], ["continue", "finish staging rollout billing"])
        self.assertTrue(row["generic_start"])
        self.assertEqual(row["outcome"], "followed")

    def test_new_topic_and_memory_miss(self) -> None:
        row = pe.score_session(
            [CURATED],
            ["write a haiku about autumn leaves", "no, I already told you the meter"],
            miss_cues=["i already told you"],
        )
        self.assertEqual(row["outcome"], "new_topic")
        self.assertTrue(row["memory_miss"])

    def test_nothing_shown(self) -> None:
        self.assertEqual(pe.score_session([], ["anything at all here"])["outcome"], "nothing_shown")


class TestShownAndSnapshots(unittest.TestCase):
    def test_only_first_injection_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = _hub(Path(tmp))
            threads = collect_open_threads(hub)
            self.assertTrue(pe.record_shown(hub, "s-1", threads, env="claude"))
            self.assertFalse(pe.record_shown(hub, "s-1", threads[:1], env="claude"))
            state = pe._load_state(hub)
            self.assertEqual(len(state["shown"]["s-1"]["threads"]), 2)

    def test_snapshot_only_on_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = _hub(Path(tmp))
            self.assertTrue(pe.record_snapshot(hub))
            self.assertFalse(pe.record_snapshot(hub))
            snap = pe._load_state(hub)["snapshots"][-1]["threads"]
            by_slug = {t["slug"]: t["curated"] for t in snap}
            self.assertEqual(by_slug, {"alpha-hub": True, "beta-app": False})


class TestEvaluateChat(unittest.TestCase):
    def setUp(self) -> None:
        lc.clear_lang_cue_cache()

    def test_waits_for_messages_then_scores_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = _hub(Path(tmp))
            pe.record_shown(hub, "chat-1", collect_open_threads(hub), env="claude")
            jsonl = _transcript(hub, "chat-1", ["finish staging rollout billing"])
            self.assertIsNone(pe.evaluate_chat(hub, jsonl, env="claude"))

            _transcript(hub, "chat-1", ["finish staging rollout billing", "now the service", "and tests"])
            row = pe.evaluate_chat(hub, jsonl, env="claude")
            self.assertEqual(row["outcome"], "followed")
            self.assertEqual(row["shown_source"], "injected")
            self.assertIsNone(pe.evaluate_chat(hub, jsonl, env="claude", final=True))
            rows = [r for r in read_metrics(hub) if r.get("event") == "pointer_outcome"]
            self.assertEqual(len(rows), 1)

    def test_cursor_uses_snapshot_taken_before_the_chat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = _hub(Path(tmp))
            pe.record_snapshot(hub, now=datetime.now() - timedelta(hours=1))
            jsonl = _transcript(hub, "cursor-1", ["tweak header gradient colors"])
            row = pe.evaluate_chat(hub, jsonl, env="cursor", final=True, workspace_slug="beta-app")
            self.assertEqual(row["shown_source"], "snapshot")
            self.assertEqual(row["best_slug"], "beta-app")
            self.assertFalse(row["best_curated"])

    def test_no_snapshot_is_not_guessed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = _hub(Path(tmp))
            jsonl = _transcript(hub, "cursor-2", ["tweak header gradient colors"])
            self.assertIsNone(pe.evaluate_chat(hub, jsonl, env="cursor", final=True))
            self.assertEqual(pe._load_state(hub)["evaluated"]["cursor-2"]["outcome"], "no_snapshot")

    def test_backlog_scores_idle_chats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = _hub(Path(tmp))
            pe.record_snapshot(hub, now=datetime.now() - timedelta(days=1))
            jsonl = _transcript(hub, "cursor-3", ["tweak header gradient colors"])
            old = time.time() - 3 * 3600
            os.utime(jsonl, (old, old))
            (hub / "chats" / "manifest.json").write_text(
                json.dumps({"processed": [{
                    "id": "cursor-3", "env": "cursor", "date": TODAY,
                    "workspace": "Users-example-Work-beta-app",
                }], "pending": []}),
                encoding="utf-8",
            )
            stats = pe.evaluate_backlog(hub)
            self.assertEqual(stats["scored"], 1)
            self.assertEqual(pe.evaluate_backlog(hub)["scored"], 0)


class TestSummarize(unittest.TestCase):
    def test_rates_split_curated_auto_and_env(self) -> None:
        rows = [
            {"event": "pointer_outcome", "chat_id": "a", "env": "claude", "outcome": "new_topic",
             "curated_shown": 1, "threads_shown": 2, "curated_score": 0.0, "auto_score": 0.0},
            # a re-score of the same chat replaces the earlier row
            {"event": "pointer_outcome", "chat_id": "a", "env": "claude", "outcome": "followed",
             "curated_shown": 1, "threads_shown": 2, "curated_score": 0.5, "auto_score": 0.0},
            {"event": "pointer_outcome", "chat_id": "b", "env": "cursor", "outcome": "new_topic",
             "curated_shown": 0, "threads_shown": 2, "curated_score": 0.0, "auto_score": 0.1,
             "memory_miss": True},
            {"event": "pointer_outcome", "chat_id": "c", "env": "cursor", "outcome": "nothing_shown"},
        ]
        s = pe.summarize(rows)
        self.assertEqual(s["sessions"], 2)
        self.assertEqual(s["followed_rate"], 0.5)
        self.assertEqual(s["curated_followed_rate"], 1.0)
        self.assertEqual(s["auto_followed_rate"], 0.0)
        self.assertEqual(s["memory_miss_rate"], 0.5)
        self.assertEqual(s["by_env"]["cursor"]["n"], 1)


class TestHookWiring(unittest.TestCase):
    def setUp(self) -> None:
        lc.clear_lang_cue_cache()

    def test_prompt_submit_records_shown_and_stop_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = _hub(Path(tmp))
            jsonl = _transcript(hub, "claude-sess-1", [
                "finish staging rollout billing", "check the service", "ship it",
            ])
            base = {"session_id": "claude-sess-1", "cwd": str(Path(tmp) / "alpha-hub"),
                    "transcript_path": str(jsonl)}
            out = bh.handle_boundary({**base, "hook_event_name": "UserPromptSubmit"}, memory_home=hub)
            self.assertEqual(out["status"], "injected")
            self.assertIn("claude-sess-1", pe._load_state(hub)["shown"])

            out = bh.handle_boundary({**base, "hook_event_name": "Stop"}, memory_home=hub)
            self.assertEqual(out["pointer_outcome"]["outcome"], "followed")
            self.assertEqual(out["pointer_outcome"]["env"], "claude")


if __name__ == "__main__":
    unittest.main()
