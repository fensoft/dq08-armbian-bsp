#!/usr/bin/env python3
"""Static security-boundary tests for the GitHub release workflows."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def job(text: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)", text
    )
    if match is None:
        raise AssertionError(f"workflow job not found: {name}")
    return match.group(1)


class WorkflowPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.release = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
        cls.verify = (WORKFLOWS / "verify.yml").read_text(encoding="utf-8")
        cls.all_workflows = "\n".join(
            path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS.glob("*.yml"))
        )

    def test_release_workflow_has_no_pull_request_trigger(self) -> None:
        event_section = self.release.split("\npermissions:", 1)[0]
        self.assertNotRegex(event_section, r"(?m)^\s+pull_request:\s*$")

    def test_pull_request_workflow_is_hosted_only(self) -> None:
        self.assertRegex(self.verify, r"(?m)^  pull_request:\s*$")
        self.assertNotIn("self-hosted", self.verify)
        self.assertNotIn("dq08-builder", self.verify)

    def test_builder_is_health_gated_and_has_no_write_or_par_credential(self) -> None:
        build = job(self.release, "build")
        self.assertIn("needs.control.outputs.runner_ready == 'true'", build)
        self.assertIn("needs['lock-state'].result == 'success'", build)
        self.assertIn("runs-on: [self-hosted, Linux, ARM64, dq08-builder]", build)
        self.assertRegex(build, r"(?ms)^    permissions:\n      actions: read\s")
        for forbidden in (
            "contents: write",
            "issues: write",
            "OCI_STAGING_PAR_URL",
            "secrets.",
            "github.token",
        ):
            self.assertNotIn(forbidden, build)

    def test_publisher_alone_gets_release_environment_and_par(self) -> None:
        publish = job(self.release, "publish")
        self.assertIn("runs-on: ubuntu-24.04", publish)
        self.assertIn("environment: release", publish)
        self.assertIn("contents: write", publish)
        self.assertIn("secrets.OCI_STAGING_PAR_URL", publish)
        self.assertEqual(self.release.count("secrets.OCI_STAGING_PAR_URL"), 1)
        self.assertNotIn("self-hosted", publish)

    def test_draft_recovery_lists_drafts_and_verifies_downloaded_bytes(self) -> None:
        publish = job(self.release, "publish")
        self.assertIn("releases?per_page=100", publish)
        self.assertGreaterEqual(publish.count("download_release_assets.sh"), 2)
        self.assertIn("--existing-draft-dir", publish)
        self.assertIn("--existing-release-dir", publish)

    def test_offline_runner_has_deduplicated_issue_path(self) -> None:
        report = job(self.release, "report")
        self.assertIn("key=runner-offline", report)
        self.assertIn("label=runner-offline", report)
        self.assertIn("upsert_issue.sh", report)

    def test_all_action_dependencies_are_full_sha_pinned(self) -> None:
        uses = re.findall(r"(?m)^\s+uses:\s+([^\s#]+)", self.all_workflows)
        self.assertTrue(uses)
        for reference in uses:
            with self.subTest(reference=reference):
                self.assertRegex(reference, r"^[^@]+@[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
