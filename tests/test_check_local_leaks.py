"""The gate that keeps personal data out of a public repo.

Everything here uses synthetic names: these tests ship publicly, so they may not
contain the very data they exist to block. The fake hub is built inside tmp.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import REPO_ROOT

_spec = importlib.util.spec_from_file_location(
    "check_local_leaks", REPO_ROOT / "scripts" / "check-local-leaks.py"
)
assert _spec and _spec.loader
clk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(clk)


class TestDerivedTerms(unittest.TestCase):
    """The denylist is derived from the hub, never written into the repo."""

    def _hub(self, slugs: list[str]) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        projects = Path(tmp.name) / "chats" / "projects"
        projects.mkdir(parents=True)
        for slug in slugs:
            (projects / f"{slug}.md").write_text("# x\n", encoding="utf-8")
        return Path(tmp.name)

    def test_project_slugs_become_terms(self) -> None:
        hub = self._hub(["zephyrworks", "quillbase-web"])
        terms = clk.hub_terms(hub)
        self.assertIn("zephyrworks", terms)
        self.assertIn("quillbase-web", terms)
        self.assertIn("quillbase", terms, "a compound slug must also flag its stem")

    def test_fictional_names_are_never_terms(self) -> None:
        hub = self._hub(["example-app", "other-app"])
        self.assertEqual(clk.hub_terms(hub), set())

    def test_product_vocabulary_is_subtracted(self) -> None:
        """The hub holds a file for this repo too. Without this, the product's
        own words are flagged on nearly every line and the check gets ignored."""
        hub = self._hub(["agent-memory-unified", "zephyrworks"])
        terms = clk.hub_terms(hub, repo=REPO_ROOT)
        self.assertNotIn("memory", terms)
        self.assertNotIn("agent-memory-unified", terms)
        self.assertIn("zephyrworks", terms)

    def test_no_hub_means_no_terms(self) -> None:
        """Public CI has no hub; the check degrades to shapes rather than failing."""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(clk.hub_terms(Path(tmp)), set())


class TestScanning(unittest.TestCase):
    def test_local_name_is_caught(self) -> None:
        hits = clk.scan_text("see the zephyrworks deploy notes", {"zephyrworks"})
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][0], 1)

    def test_real_home_path_is_caught_without_any_list(self) -> None:
        hits = clk.scan_text("cd /Users/jsmith/Work/thing", set())
        self.assertTrue(hits, "shape checks must work with an empty denylist")

    def test_doc_placeholders_are_not_flagged(self) -> None:
        """`/Users/you/…` is an instruction to the reader, not an account."""
        for line in ("/Users/you/.agent-memory", "/home/example-user/hub", "/Users/username/x"):
            with self.subTest(line=line):
                self.assertEqual(clk.scan_text(line, set()), [])

    def test_encoded_denylist_is_caught(self) -> None:
        """The previous fix obfuscated the names instead of removing them."""
        hits = clk.scan_text('_DENY_CODES = [(116, 114)]', set())
        self.assertTrue(hits)


class TestPushGate(unittest.TestCase):
    """A leak already shipped inside a tag whose content was on no branch."""

    def _repo(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Path(tmp.name)
        for args in (["init", "-q"], ["config", "user.email", "t@example.com"],
                     ["config", "user.name", "t"]):
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
        return repo

    def _commit(self, repo: Path, name: str, body: str) -> None:
        (repo / name).write_text(body, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "x"], cwd=repo, check=True, capture_output=True
        )

    def _run(self, repo: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "check-local-leaks.py"),
             "--repo", str(repo), *args],
            capture_output=True,
            text=True,
        )

    def test_tag_tree_is_scanned(self) -> None:
        repo = self._repo()
        self._commit(repo, "DOC.md", "clean\n")
        self._commit(repo, "DOC.md", "run it from /Users/jsmith/Work/app\n")
        subprocess.run(["git", "tag", "v1"], cwd=repo, check=True, capture_output=True)
        self.assertEqual(self._run(repo, "--rev", "v1").returncode, 1)

    def test_range_only_reports_added_lines(self) -> None:
        """An old file this push does not touch is already public — re-flagging
        it every time would train the maintainer to use --no-verify."""
        repo = self._repo()
        self._commit(repo, "OLD.md", "legacy /Users/jsmith/Work/app\n")
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
        ).stdout.strip()
        self._commit(repo, "NEW.md", "all clean here\n")
        self.assertEqual(self._run(repo, "--range", f"{base}..HEAD").returncode, 0)

    def test_range_catches_a_newly_added_line(self) -> None:
        repo = self._repo()
        self._commit(repo, "DOC.md", "clean\n")
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
        ).stdout.strip()
        self._commit(repo, "DOC.md", "clean\nnow with /Users/jsmith/Work/app\n")
        result = self._run(repo, "--range", f"{base}..HEAD")
        self.assertEqual(result.returncode, 1)
        self.assertIn("DOC.md:2", result.stderr, "line number must be the real one")

    def test_findings_are_redacted_by_default(self) -> None:
        """Findings print in public CI logs — the match must not be echoed."""
        repo = self._repo()
        self._commit(repo, "DOC.md", "run from /Users/jsmith/Work/app\n")
        result = self._run(repo, "--rev", "HEAD")
        self.assertIn("[redacted]", result.stderr)
        self.assertNotIn("jsmith", result.stderr)


class TestFileTypeCoverage(unittest.TestCase):
    """A leak must fail in every text file, not only the ones we thought of.

    Scanning was gated on an extension allowlist, so the identical finding that
    failed in a .md passed in .js, .html, .jsonl and an extension-less script.
    .jsonl is the transcript format a live token was once found in.
    """

    def _scanned(self, name: str) -> bool:
        return clk._should_scan(name)

    def test_text_types_outside_the_old_allowlist_are_scanned(self) -> None:
        for name in ("app.js", "dump.html", "chat.jsonl", "deploy", "styles.css",
                     "index.ts", "Makefile", ".gitignore", "notes.md"):
            with self.subTest(name=name):
                self.assertTrue(self._scanned(name))

    def test_binary_payloads_are_skipped(self) -> None:
        for name in ("logo.png", "font.woff2", "archive.zip", "lib.dylib", "clip.mp4"):
            with self.subTest(name=name):
                self.assertFalse(self._scanned(name))

    def test_binary_suffix_match_is_case_insensitive(self) -> None:
        self.assertFalse(self._scanned("PHOTO.PNG"))

    def test_self_exempt_files_stay_skipped(self) -> None:
        self.assertFalse(self._scanned("CHANGELOG.md"))
        self.assertFalse(self._scanned("scripts/check-local-leaks.py"))


if __name__ == "__main__":
    unittest.main()
