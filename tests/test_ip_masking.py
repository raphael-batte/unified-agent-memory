"""Public IPv4 masking on the distill path (lib/secrets_guard.py)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.secrets_guard import IP_PLACEHOLDER, mask_public_ips, sanitize_message, scan_file  # noqa: E402


class TestIpMasking(unittest.TestCase):
    def test_public_masked_private_kept(self) -> None:
        text, n = mask_public_ips("old box 203.0.114.7, new box 198.51.99.20; local 127.0.0.1 and 10.0.0.5")
        self.assertEqual(n, 2)
        self.assertNotIn("203.0.114.7", text)
        self.assertIn("127.0.0.1", text)
        self.assertIn("10.0.0.5", text)

    def test_versions_and_invalid_left_alone(self) -> None:
        for raw in ("v0.29.7", "release 1.2.3.4.5", "999.1.1.1", "build 2026.10.13"):
            self.assertEqual(mask_public_ips(raw), (raw, 0), raw)

    def test_sanitize_masks_and_keeps_message(self) -> None:
        clean, _n = sanitize_message("the new prod host is 203.0.114.7, move the DNS there")
        self.assertIn(IP_PLACEHOLDER, clean)
        self.assertIn("move the DNS there", clean)

    def test_opt_out(self) -> None:
        with mock.patch.dict(os.environ, {"AGENT_MEMORY_MASK_IP": "0"}):
            self.assertEqual(mask_public_ips("host 203.0.114.7")[1], 0)

    def test_not_a_secret_for_hub_scans(self) -> None:
        """infra.md legitimately lists addresses; verify-memory must not flag it."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "infra.md"
            path.write_text("- prod: 203.0.114.7 (ssh deploy@)\n", encoding="utf-8")
            self.assertEqual(scan_file(path), [])


if __name__ == "__main__":
    unittest.main()
