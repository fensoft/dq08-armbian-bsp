from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import SCRIPTS, make_release_fixture  # noqa: E402


class ManifestValidationTests(unittest.TestCase):
    def run_create_manifest(
        self, fixture, run_id: str = "123"
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "create_manifest.py"),
                "--bsp-root",
                str(fixture.bsp),
                "--armbian-root",
                str(fixture.armbian),
                "--preflight",
                str(fixture.preflight_path),
                "--stage-dir",
                str(fixture.stage),
                "--workflow-run-id",
                run_id,
                "--workflow-run-attempt",
                "1",
            ],
            text=True,
            capture_output=True,
        )

    def create_manifest(self, fixture, run_id: str = "123") -> dict:
        result = self.run_create_manifest(fixture, run_id)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def rename_stage_image(
        self, fixture, image_name: str, *, update_manifest: bool = False
    ) -> None:
        old_image = fixture.image
        old_checksum = Path(f"{old_image}.sha")
        old_metadata = fixture.stage / f"{old_image.name.removesuffix('.xz')}.txt"
        new_image = fixture.stage / image_name
        new_checksum = fixture.stage / f"{image_name}.sha"
        new_metadata = fixture.stage / f"{image_name.removesuffix('.xz')}.txt"
        old_image.rename(new_image)
        old_checksum.rename(new_checksum)
        old_metadata.rename(new_metadata)
        image_sha = hashlib.sha256(new_image.read_bytes()).hexdigest()
        new_checksum.write_text(
            f"{image_sha}  {image_name}\n", encoding="utf-8"
        )
        fixture.image = new_image

        if update_manifest:
            manifest_path = fixture.stage / "build-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["image"].update(
                {
                    "filename": new_image.name,
                    "checksum_filename": new_checksum.name,
                    "metadata_filename": new_metadata.name,
                }
            )
            manifest["assets"] = {
                path.name: {
                    "role": role,
                    "size_bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                for path, role in (
                    (new_image, "image"),
                    (new_checksum, "checksum"),
                    (new_metadata, "metadata"),
                )
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def validate(self, fixture, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "validate_release.py"),
                "--stage-dir",
                str(fixture.stage),
                "--module-conf",
                str(fixture.bsp / "module.conf"),
                *extra,
            ],
            text=True,
            capture_output=True,
        )

    def test_manifest_records_exact_sources_assets_and_untested_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = make_release_fixture(Path(temporary))
            manifest = self.create_manifest(fixture)
            self.assertFalse(manifest["hardware_tested"])
            self.assertEqual(manifest["release_name"], "dq08-armbian-v26.5.1-bsp-v1.2.3")
            self.assertEqual(manifest["armbian"]["version"], "26.5.1")
            self.assertEqual(
                manifest["armbian"]["framework_version"], "26.05.0-trunk"
            )
            self.assertEqual(manifest["bsp"]["version"], "1.2.3")
            self.assertIn(
                "_26.05.0-trunk-bsp-v1.2.3_Vontar-dq08_",
                manifest["image"]["filename"],
            )
            self.assertEqual(manifest["kernel"]["commit"], fixture.preflight["kernel"]["commit"])
            self.assertEqual(manifest["uboot"]["commit"], fixture.module_values["DQ08_UBOOT_COMMIT"])
            self.assertEqual(manifest["rkbin"]["commit"], fixture.module_values["DQ08_RKBIN_COMMIT"])
            self.assertEqual(len(manifest["assets"]), 3)
            self.assertEqual(len(list(fixture.stage.iterdir())), 4)

    def test_hosted_validation_checks_xz_checksum_metadata_and_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = make_release_fixture(Path(temporary))
            self.create_manifest(fixture)
            result = self.validate(
                fixture, "--expected-preflight", str(fixture.preflight_path)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "validated")
            self.assertTrue(payload["should_publish"])
            self.assertEqual(len(payload["assets"]), 4)

    def test_manifest_creation_rejects_invalid_release_filename(self) -> None:
        invalid_names = (
            "Armbian_26.05.0-trunk_Vontar-dq08_bookworm_current_6.18.40_minimal.img.xz",
            "Armbian_26.05.0-trunk-bsp-v9.9.9_Vontar-dq08_bookworm_current_6.18.40_minimal.img.xz",
            "Armbian_26.5.1-bsp-v1.2.3_Vontar-dq08_bookworm_current_6.18.40_minimal.img.xz",
        )
        for image_name in invalid_names:
            with (
                self.subTest(image_name=image_name),
                tempfile.TemporaryDirectory() as temporary,
            ):
                fixture = make_release_fixture(Path(temporary))
                self.rename_stage_image(fixture, image_name)
                result = self.run_create_manifest(fixture)
                self.assertEqual(result.returncode, 2)
                self.assertIn("filename", result.stderr.lower())

    def test_hosted_validation_rejects_invalid_release_filename(self) -> None:
        invalid_names = (
            "Armbian_26.05.0-trunk_Vontar-dq08_bookworm_current_6.18.40_minimal.img.xz",
            "Armbian_26.05.0-trunk-bsp-v9.9.9_Vontar-dq08_bookworm_current_6.18.40_minimal.img.xz",
            "Armbian_26.5.1-bsp-v1.2.3_Vontar-dq08_bookworm_current_6.18.40_minimal.img.xz",
        )
        for image_name in invalid_names:
            with (
                self.subTest(image_name=image_name),
                tempfile.TemporaryDirectory() as temporary,
            ):
                fixture = make_release_fixture(Path(temporary))
                self.create_manifest(fixture)
                self.rename_stage_image(
                    fixture, image_name, update_manifest=True
                )
                result = self.validate(fixture)
                self.assertEqual(result.returncode, 2)
                self.assertIn("filename", result.stderr.lower())

    def test_checksum_corruption_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = make_release_fixture(Path(temporary))
            self.create_manifest(fixture)
            checksum = next(fixture.stage.glob("*.img.xz.sha"))
            checksum.write_text(f"{'0' * 64}  {fixture.image.name}\n", encoding="utf-8")
            result = self.validate(fixture)
            self.assertEqual(result.returncode, 2)
            self.assertIn("checksum", result.stderr.lower())

    def test_extra_asset_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = make_release_fixture(Path(temporary))
            self.create_manifest(fixture)
            (fixture.stage / "unexpected.txt").write_text("no\n", encoding="utf-8")
            result = self.validate(fixture)
            self.assertEqual(result.returncode, 2)
            self.assertIn("exactly four", result.stderr)

    def test_existing_identical_release_ignores_workflow_run_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = make_release_fixture(Path(temporary))
            self.create_manifest(fixture)
            existing = fixture.root / "existing"
            shutil.copytree(fixture.stage, existing)
            manifest_path = fixture.stage / "build-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["build"]["workflow"] = {
                "run_id": "999",
                "run_attempt": 7,
                "run_url": "https://example.invalid/run/999",
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self.validate(
                fixture, "--existing-release-dir", str(existing)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "already_published")
            self.assertFalse(payload["should_publish"])

    def test_existing_release_with_different_source_is_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = make_release_fixture(Path(temporary))
            self.create_manifest(fixture)
            existing = fixture.root / "existing"
            shutil.copytree(fixture.stage, existing)
            manifest_path = fixture.stage / "build-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["kernel"]["commit"] = "f" * 40
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self.validate(
                fixture, "--existing-release-dir", str(existing)
            )
            self.assertEqual(result.returncode, 4, result.stderr)
            self.assertIn("different provenance or assets", result.stderr)

    def test_partial_draft_ignores_only_workflow_run_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = make_release_fixture(Path(temporary))
            self.create_manifest(fixture)
            draft = fixture.root / "draft"
            draft.mkdir()
            shutil.copy2(fixture.image, draft / fixture.image.name)
            shutil.copy2(
                fixture.stage / "build-manifest.json",
                draft / "build-manifest.json",
            )
            manifest_path = fixture.stage / "build-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["build"]["workflow"] = {
                "run_id": "999",
                "run_attempt": 7,
                "run_url": "https://example.invalid/run/999",
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = self.validate(
                fixture,
                "--expected-preflight",
                str(fixture.preflight_path),
                "--existing-draft-dir",
                str(draft),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "validated_draft")
            self.assertTrue(payload["should_publish"])

    def test_partial_draft_with_changed_asset_is_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = make_release_fixture(Path(temporary))
            self.create_manifest(fixture)
            draft = fixture.root / "draft"
            shutil.copytree(fixture.stage, draft)
            (draft / fixture.image.name).write_bytes(b"different image")
            result = self.validate(
                fixture, "--existing-draft-dir", str(draft)
            )
            self.assertEqual(result.returncode, 4, result.stderr)
            self.assertIn("draft asset differs", result.stderr)

    def test_expected_preflight_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = make_release_fixture(Path(temporary))
            self.create_manifest(fixture)
            expected = json.loads(fixture.preflight_path.read_text())
            expected["armbian"]["commit"] = "f" * 40
            changed = fixture.root / "changed-preflight.json"
            changed.write_text(json.dumps(expected), encoding="utf-8")
            result = self.validate(fixture, "--expected-preflight", str(changed))
            self.assertEqual(result.returncode, 2)
            self.assertIn("Armbian provenance", result.stderr)


if __name__ == "__main__":
    unittest.main()
