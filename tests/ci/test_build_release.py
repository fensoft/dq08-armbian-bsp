from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts/ci"))

import build_release  # noqa: E402
from _lib import ReleaseError  # noqa: E402


class BuildReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = {
            "DQ08_BOARD": "vontar-dq08",
            "DQ08_MAINTAINER": "fensoft",
            "DQ08_MAINTAINER_EMAIL": "fensoft@users.noreply.github.com",
        }

    def test_commands_rebuild_only_kernel_and_uboot_artifacts(self) -> None:
        kernel, uboot, image = build_release.build_commands(
            Path("/bsp"), Path("/armbian"), self.module, "a" * 40
        )
        self.assertEqual(kernel[1], "kernel")
        self.assertIn("ARTIFACT_IGNORE_CACHE=yes", kernel)
        self.assertIn("CLEAN_LEVEL=make-kernel", kernel)
        self.assertEqual(uboot[1], "uboot")
        self.assertIn("ARTIFACT_IGNORE_CACHE=yes", uboot)
        self.assertIn("CLEAN_LEVEL=make-uboot", uboot)
        self.assertNotIn("ARTIFACT_IGNORE_CACHE=yes", image)
        self.assertNotIn("CLEAN_LEVEL=make-kernel", image)
        self.assertIn("COMPRESS_OUTPUTIMAGE=sha,xz", image)
        self.assertIn("IMAGE_XZ_COMPRESSION_RATIO=1", image)
        self.assertNotIn("--allow-unsupported", kernel + uboot + image)

    def test_stages_only_one_new_image_and_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            images = root / "images"
            images.mkdir()
            old = images / "old.img.xz"
            old.write_bytes(b"old")
            before = build_release.snapshot_images(images)
            new = images / "new.img.xz"
            new.write_bytes(b"new")
            (images / "new.img.xz.sha").write_text("checksum\n", encoding="utf-8")
            (images / "new.img.txt").write_text("metadata\n", encoding="utf-8")
            stage = root / "stage"
            staged = build_release.stage_new_image(images, before, stage)
            self.assertEqual({path.name for path in staged}, {"new.img.xz", "new.img.xz.sha", "new.img.txt"})
            self.assertFalse((stage / "old.img.xz").exists())

    def test_refuses_ambiguous_or_nonempty_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            images = root / "images"
            images.mkdir()
            before = {}
            for stem in ("one", "two"):
                (images / f"{stem}.img.xz").write_bytes(stem.encode())
                (images / f"{stem}.img.xz.sha").write_text("checksum\n", encoding="utf-8")
                (images / f"{stem}.img.txt").write_text("metadata\n", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseError, "exactly one"):
                build_release.stage_new_image(images, before, root / "stage")


if __name__ == "__main__":
    unittest.main()
