from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts/ci"))

import discover_release  # noqa: E402
from _lib import ReleaseError  # noqa: E402


class DiscoverReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tags = {
            "v26.5.0": "0" * 40,
            "v26.5.1": "1" * 40,
            "v26.5.2": "2" * 40,
            "v26.10.0": "a" * 40,
            "v26.5.3-trunk": "3" * 40,
            "v26.6.0-rc1": "4" * 40,
        }
        self.empty_state = {"schema_version": 1, "armbian_tags": {}}

    @staticmethod
    def complete_release(tag: str, *, assets_as_objects: bool = False) -> dict:
        image = "Armbian_Vontar-dq08_bookworm_current_6.18.40_minimal.img.xz"
        assets: list[object] = [
            image,
            f"{image}.sha",
            f"{image.removesuffix('.xz')}.txt",
            "build-manifest.json",
        ]
        if assets_as_objects:
            assets = [{"name": name} for name in assets]
        return {
            "tag_name": tag,
            "name": tag,
            "draft": False,
            "prerelease": False,
            "assets": assets,
        }

    def test_selects_oldest_unpublished_stable_at_baseline(self) -> None:
        published = {"dq08-armbian-v26.5.1-bsp-v1.0.1"}
        result, state = discover_release.discover(
            self.tags, published, self.empty_state, "1.0.1"
        )
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["armbian_tag"], "v26.5.2")
        self.assertFalse(result["already_published"])
        self.assertNotIn("v26.5.0", state["armbian_tags"])
        self.assertNotIn("v26.5.3-trunk", state["armbian_tags"])

    def test_reports_up_to_date(self) -> None:
        published = {
            "dq08-armbian-v26.5.1-bsp-v1.0.1",
            "dq08-armbian-v26.5.2-bsp-v1.0.1",
            "dq08-armbian-v26.10.0-bsp-v1.0.1",
        }
        result, _ = discover_release.discover(
            self.tags, published, self.empty_state, "v1.0.1"
        )
        self.assertEqual(result["status"], "up_to_date")
        self.assertFalse(result["should_build"])
        self.assertIsNone(result["armbian_tag"])

    def test_rejects_moved_recorded_tag(self) -> None:
        state = {"schema_version": 1, "armbian_tags": {"v26.5.1": "f" * 40}}
        with self.assertRaisesRegex(ReleaseError, "tag moved"):
            discover_release.discover(self.tags, set(), state, "1.0.1")

    def test_rejects_disappeared_recorded_tag(self) -> None:
        state = {"schema_version": 1, "armbian_tags": {"v26.9.0": "f" * 40}}
        with self.assertRaisesRegex(ReleaseError, "disappeared"):
            discover_release.discover(self.tags, set(), state, "1.0.1")

    def test_manual_request_selects_existing_release_for_idempotency(self) -> None:
        published = {"dq08-armbian-v26.5.2-bsp-v1.0.1"}
        result, _ = discover_release.discover(
            self.tags,
            published,
            self.empty_state,
            "1.0.1",
            requested_tag="v26.5.2",
        )
        self.assertTrue(result["should_build"])
        self.assertTrue(result["already_published"])
        self.assertEqual(result["armbian_commit"], "2" * 40)

    def test_manual_request_must_be_stable_present_and_new_enough(self) -> None:
        for requested, message in (
            ("v26.6.0-rc1", "not a stable"),
            ("v26.5.0", "older than baseline"),
            ("v26.7.0", "was not found"),
        ):
            with self.subTest(requested=requested):
                with self.assertRaisesRegex(ReleaseError, message):
                    discover_release.discover(
                        self.tags,
                        set(),
                        self.empty_state,
                        "1.0.1",
                        requested_tag=requested,
                    )

    def test_cli_writes_selection_and_next_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tags = root / "tags.json"
            releases = root / "releases.json"
            output = root / "selection.json"
            state = root / "next-state.json"
            tags.write_text(json.dumps(self.tags), encoding="utf-8")
            releases.write_text("[]", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPOSITORY_ROOT / "scripts/ci/discover_release.py"),
                    "--tags-json",
                    str(tags),
                    "--releases-json",
                    str(releases),
                    "--module-conf",
                    str(REPOSITORY_ROOT / "module.conf"),
                    "--output",
                    str(output),
                    "--next-state",
                    str(state),
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(json.loads(result.stdout), json.loads(output.read_text()))
            self.assertIn("v26.5.1", json.loads(state.read_text())["armbian_tags"])

    def test_release_list_counts_only_complete_final_four_asset_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            releases = Path(temporary) / "releases.json"
            complete_tag = "dq08-armbian-v26.5.1-bsp-v1.0.1"
            object_asset_tag = "dq08-armbian-v26.5.2-bsp-v1.0.1"
            releases.write_text(
                json.dumps(
                    [
                        self.complete_release(complete_tag),
                        self.complete_release(object_asset_tag, assets_as_objects=True),
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                discover_release.release_names(releases),
                {complete_tag, object_asset_tag},
            )

    def test_malformed_matching_releases_remain_selected(self) -> None:
        expected = "dq08-armbian-v26.5.1-bsp-v1.0.1"
        complete = self.complete_release(expected)
        malformed: list[object] = []
        draft = dict(complete, draft=True)
        prerelease = dict(complete, prerelease=True)
        partial = dict(complete, assets=complete["assets"][:3])
        mismatched = dict(
            complete,
            assets=[
                complete["assets"][0],
                "different.img.xz.sha",
                complete["assets"][2],
                "build-manifest.json",
            ],
        )
        extra = dict(complete, assets=[*complete["assets"], "unexpected.txt"])
        missing_metadata = {"tag_name": expected, "name": expected}
        malformed.extend((draft, prerelease, partial, mismatched, extra, missing_metadata, expected))

        with tempfile.TemporaryDirectory() as temporary:
            releases = Path(temporary) / "releases.json"
            for item in malformed:
                with self.subTest(item=item):
                    releases.write_text(json.dumps([item]), encoding="utf-8")
                    published = discover_release.release_names(releases)
                    result, _ = discover_release.discover(
                        {"v26.5.1": "1" * 40},
                        published,
                        self.empty_state,
                        "1.0.1",
                    )
                    self.assertEqual(result["status"], "selected")
                    self.assertFalse(result["already_published"])


if __name__ == "__main__":
    unittest.main()
