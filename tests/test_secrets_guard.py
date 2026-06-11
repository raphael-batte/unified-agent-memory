"""Tests for scripts/lib/secrets_guard.py and distill redaction."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib import secrets_guard as sg  # noqa: E402
from helpers import REPO_ROOT, load_script_module, minimal_hub

de = load_script_module("distill_extract", "distill-extract.py")
vm = load_script_module("verify_memory", "verify-memory.py")


class TestSecretsGuard(unittest.TestCase):
    def test_redact_password_assignment(self) -> None:
        text = "set DB_PASSWORD=supersecret123 in wp-config"
        out, n = sg.redact_secrets(text)
        self.assertGreater(n, 0)
        self.assertNotIn("supersecret123", out)
        self.assertIn(sg.REDACTED_PLACEHOLDER, out)

    def test_redact_github_token(self) -> None:
        text = "token ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        out, _ = sg.redact_secrets(text)
        self.assertNotIn("ghp_", out)

    def test_drop_env_only_message(self) -> None:
        clean, _ = sg.sanitize_message("copy .env to server")
        self.assertIsNone(clean)

    def test_scan_file_finds_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leak.md"
            path.write_text("password: hunter2\n", encoding="utf-8")
            hits = sg.scan_file(path)
            self.assertEqual(len(hits), 1)
            self.assertIn(hits[0][1], ("password_assignment", "password_colon"))

    def test_distill_extract_redacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chat.jsonl"
            line = json.dumps(
                {
                    "role": "user",
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": "<user_query>api_key=abc123secretkey — deploy decision context padding</user_query>",
                            }
                        ]
                    },
                }
            )
            path.write_text(line + "\n", encoding="utf-8")
            data = de.build_extract(path, projects_root=Path(tmp), strategy="all")
            self.assertGreater(data["secrets_redacted"], 0)
            blob = json.dumps(data)
            self.assertNotIn("abc123secretkey", blob)

    def test_provider_token_prefixes_detected(self) -> None:
        # All values are SYNTHETIC fakes (format-valid, marked EXAMPLE). The token
        # prefix is split across `+` concatenation so the committed file contains
        # no contiguous token literal — this avoids GitHub push-protection / secret
        # scanner false positives while the runtime string still drives the regex.
        # Never paste a real/captured secret into tests in a public repo.
        samples = {
            "google_oauth_client_secret": "GOCSPX" + "-EXAMPLE_fake_client_secret_value",
            "google_recaptcha_key": "6L" + "eEXAMPLEfakeRecaptchaKey0000000000000x",
            "google_api_key": "AIza" + "EXAMPLEfakeGoogleApiKey00000000000000",
            "grafana_service_account_token": "glsa_" + "EXAMPLEfakeServiceAccountToken000000",
            "grafana_cloud_token": "glc_" + "EXAMPLEfakeGrafanaCloudAccessToken00",
            "grafana_legacy_api_key": "eyJrIjoi" + "EXAMPLEfakeGrafanaLegacyApiKey00",
            "slack_token": "xoxb" + "-EXAMPLE-fake-slack-bot-token-000000",
            "github_finegrained_pat": "github_" + "pat_" + "EXAMPLEfakeFineGrainedPat" + "0" * 40,
            "gitlab_pat": "glpat" + "-EXAMPLEfakeGitlabPat00",
            "stripe_secret_key": "sk_" + "live_EXAMPLEfakeStripeSecretKey00",
            "sendgrid_key": "SG." + "EXAMPLEfakeSendgridIdPart.EXAMPLEfakeSendgridSecretPart",
            "npm_token": "npm_" + "EXAMPLEfakeNpmAutomationToken0000000",
            "pypi_token": "pypi-" + "AgEIEXAMPLEfakePypiUploadToken00",
        }
        for label, value in samples.items():
            with self.subTest(label=label):
                self.assertIn(label, sg.find_secret_labels(value))
                out, n = sg.redact_secrets(value)
                self.assertGreater(n, 0)
                self.assertNotIn(value, out)

    def test_url_encoded_secret_redacted(self) -> None:
        # Real-world regression: a secret embedded in a URL-encoded blob has a
        # word char (from %22) immediately before its prefix, so \b anchors miss it.
        # Value is a SYNTHETIC fake matching the GOCSPX- format (prefix split via
        # concatenation so no contiguous token literal is committed).
        secret = "GOCSPX" + "-EXAMPLE_fake_client_secret_value"
        blob = f"client_secret%22:%22{secret}%22,%22redirect"
        self.assertIn("google_oauth_client_secret", sg.find_secret_labels(blob))
        out, _ = sg.redact_secrets(blob)
        self.assertNotIn(secret, out)
        self.assertNotIn("GOCSPX" + "-EXAMPLE", out)

    def test_provider_prefixes_no_false_positives(self) -> None:
        for benign in (
            "tilt-0123example4567",
            "describe the function",
            "skyscraper-image asset",
            "glsa is a common prefix word",
        ):
            with self.subTest(benign=benign):
                self.assertEqual(sg.find_secret_labels(benign), [])

    def test_entropy_strict_finds_token(self) -> None:
        token = "AbcdefGH1234567890klmnopQRSTuv"
        self.assertTrue(sg.find_entropy_secrets(f"value={token}"))

    def test_strict_scan_optional(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "entropy.md"
            token = "A" * 28 + "BBBBCCCC"
            path.write_text(f"key material {token}\n", encoding="utf-8")
            strict_hits = sg.scan_file_strict(path)
            plain_hits = sg.scan_file(path)
            self.assertGreaterEqual(len(strict_hits), len(plain_hits))

    def test_verify_fails_on_secret_in_hub(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            minimal_hub(hub, projects=1)
            bad = hub / "feedback" / "wins.md"
            bad.write_text("## T\n\n+ used password: hunter2\n", encoding="utf-8")
            r = vm.check_no_secrets(hub)
            self.assertFalse(r.ok)


if __name__ == "__main__":
    unittest.main()
