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
        cls.builder_health = (WORKFLOWS / "builder-health.yml").read_text(
            encoding="utf-8"
        )
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

    def test_builder_is_health_gated_and_has_no_github_write_credential(self) -> None:
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

    def test_local_write_par_is_file_only_fail_closed_and_integrity_checked(self) -> None:
        build = job(self.release, "build")
        local_par_file = "/etc/dq08-builder-write-par-url"
        for workflow_name, runner_job in (
            ("build", build),
            ("health", self.builder_health),
        ):
            with self.subTest(workflow=workflow_name):
                self.assertIn(
                    'upload_mode="${DQ08_STAGING_UPLOAD_MODE:-instance-principal}"',
                    runner_job,
                )
                self.assertIn("instance-principal)", runner_job)
                self.assertIn("write-par)", runner_job)
                self.assertIn(local_par_file, runner_job)
                self.assertIn(
                    '''stat -c '%u:%g:%a' "${par_file}")" == "0:$(id -g):440"''',
                    runner_job,
                )
                self.assertIn("Content-MD5:", runner_job)
                self.assertIn("--data-binary @", runner_job)
                self.assertIn("Unsupported DQ08_STAGING_UPLOAD_MODE", runner_job)
                self.assertIn('write_par_url="${par_lines[0]}"', runner_job)
                self.assertIn('parsed.scheme == "https"', runner_job)
                self.assertIn(
                    'parsed.netloc == f"objectstorage.{region}.oraclecloud.com"',
                    runner_job,
                )
                self.assertIn("unquote(parts[4]) == namespace", runner_job)
                self.assertIn("unquote(parts[6]) == bucket", runner_job)
                self.assertIn('parts[7] == "o"', runner_job)
                self.assertIn("EXPECTED_STAGING_PREFIX", runner_job)
                self.assertNotIn("secrets.", runner_job)
                self.assertNotIn("github.token", runner_job)
                self.assertNotIn("GITHUB_ENV", runner_job.split("write-par)", 1)[1])
                self.assertNotIn("--verbose", runner_job)
                self.assertIn("--show-error", runner_job)
                self.assertIn("--max-time", runner_job)
                self.assertEqual(runner_job.count("${write_par_url}"), 4)
                self.assertNotRegex(
                    runner_job,
                    r"(?m)(echo|printf).*\$\{write_par_url\}.*>&2",
                )
                self.assertNotRegex(
                    runner_job,
                    r"(?m)^\s+[A-Z0-9_]*WRITE[A-Z0-9_]*PAR[A-Z0-9_]*:\s*",
                )
        self.assertEqual(self.release.count(local_par_file), 1)
        self.assertEqual(self.builder_health.count(local_par_file), 1)

    def test_staging_object_is_unique_to_the_run_attempt(self) -> None:
        staging_object = (
            "dq08/${{ github.repository_id }}/"
            "${{ needs.control.outputs.release_name }}/"
            "${{ github.run_id }}-${{ github.run_attempt }}/release.tar"
        )
        self.assertEqual(self.release.count(f"STAGING_OBJECT: {staging_object}"), 2)
        build = job(self.release, "build")
        self.assertIn('[[ "${STAGING_OBJECT}" == "${expected_staging_object}" ]]', build)
        self.assertIn('[[ "${MAX_ATTEMPTS}" =~ ^[123]$ ]]', build)
        self.assertIn("--speed-limit 1024", build)
        self.assertIn("--speed-time 300", build)

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
