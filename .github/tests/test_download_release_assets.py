#!/usr/bin/env python3
"""Behavior tests for authenticated release-asset downloads."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / ".github" / "scripts" / "download_release_assets.sh"


class DownloadReleaseAssetsTests(unittest.TestCase):
    def test_downloads_only_declared_safe_asset_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            gh = fake_bin / "gh"
            gh.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
case "${!#}" in
  */101) printf 'image-bytes' ;;
  */102) printf '{"schema_version":1}' ;;
  *) exit 9 ;;
esac
""",
                encoding="utf-8",
            )
            gh.chmod(0o755)
            release = root / "release.json"
            release.write_text(
                json.dumps(
                    {
                        "assets": [
                            {
                                "id": 101,
                                "name": "image.img.xz",
                                "size": 11,
                                "state": "uploaded",
                            },
                            {
                                "id": 102,
                                "name": "build-manifest.json",
                                "size": 20,
                                "state": "uploaded",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            destination = root / "download"
            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{fake_bin}:{env['PATH']}",
                    "GH_TOKEN": "test-token",
                    "GITHUB_REPOSITORY": "owner/repository",
                }
            )
            result = subprocess.run(
                [str(HELPER), str(release), str(destination)],
                text=True,
                capture_output=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((destination / "image.img.xz").read_bytes(), b"image-bytes")
            self.assertEqual(
                (destination / "build-manifest.json").read_text(encoding="utf-8"),
                '{"schema_version":1}',
            )

    def test_rejects_unsafe_remote_asset_name_before_download(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = root / "release.json"
            release.write_text(
                json.dumps(
                    {
                        "assets": [
                            {
                                "id": 101,
                                "name": "../escape",
                                "size": 1,
                                "state": "uploaded",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            env = os.environ.copy()
            env.update(
                {
                    "GH_TOKEN": "test-token",
                    "GITHUB_REPOSITORY": "owner/repository",
                }
            )
            result = subprocess.run(
                [str(HELPER), str(release), str(root / "download")],
                text=True,
                capture_output=True,
                env=env,
            )
            self.assertEqual(result.returncode, 2, result.stderr)


if __name__ == "__main__":
    unittest.main()
