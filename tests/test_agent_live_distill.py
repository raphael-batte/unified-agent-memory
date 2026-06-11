"""Tests for agent live distill (*-live.md)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.agent_live_distill import (  # noqa: E402
    enrich_extract_with_agent_live,
    find_agent_live_file,
    live_staging_path,
    parse_agent_live_file,
)
from lib.forward_pointer import extract_forward_pointer_result  # noqa: E402
from lib.pointer_provenance import (  # noqa: E402
    PROVENANCE_AGENT_LIVE,
    pointer_provenance_class,
)


class TestAgentLiveDistill(unittest.TestCase):
    def test_parse_and_enrich(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            staging = hub / "chats" / "merge-staging"
            staging.mkdir(parents=True)
            live = live_staging_path(
                hub, slug="app", date_slug="2026-06-08", chat_id="abcd1234-uuid"
            )
            live.write_text(
                "## Summary\n\n- Shipped pointer adherence\n\n"
                "## Next step candidate\n\n- Tag and publish v0.18.0\n",
                encoding="utf-8",
            )
            parsed = parse_agent_live_file(live)
            self.assertEqual(parsed["summary"], "Shipped pointer adherence")
            self.assertEqual(parsed["next_step"], "Tag and publish v0.18.0")

            found = find_agent_live_file(hub, slug="app", chat_id="abcd1234-uuid")
            self.assertEqual(found, live)

            extract = enrich_extract_with_agent_live(
                {"workspace_slug": "app", "first_query": "old"},
                memory_home=hub,
                chat_id="abcd1234-uuid",
            )
            self.assertEqual(extract["final_summary"], "Shipped pointer adherence")
            ptr = extract_forward_pointer_result(extract)
            self.assertEqual(ptr.text, "Tag and publish v0.18.0")
            self.assertEqual(ptr.source, "agent_live")
            self.assertEqual(
                pointer_provenance_class("agent_live"), PROVENANCE_AGENT_LIVE
            )


if __name__ == "__main__":
    unittest.main()
