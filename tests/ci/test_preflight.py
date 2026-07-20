from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts/ci"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import preflight  # noqa: E402
from _lib import ReleaseError  # noqa: E402
from support import make_executable, make_release_fixture  # noqa: E402


def config_fixture(values: dict[str, str]) -> dict[str, object]:
    return {
        "ARCH": "arm64",
        "DISTRIBUTION": "Debian",
        "KERNEL_MAJOR_MINOR": "6.18",
        "KERNELPATCHDIR": "archive/rockchip64-6.18",
        "LINUXFAMILY": "rockchip64",
        "BOOT_FDT_FILE": "rockchip/rk3528-vontar-dq08.dtb",
        "BOARD_MAINTAINER": values["DQ08_MAINTAINER"],
        "BOOTBRANCH": f'commit:{values["DQ08_UBOOT_COMMIT"]}',
        "BOOTPATCHDIR": "v2026.04",
        "DQ08_RKBIN_COMMIT": values["DQ08_RKBIN_COMMIT"],
        "DQ08_RKBIN_DDR_SHA256": values["DQ08_RKBIN_DDR_SHA256"],
        "DQ08_RKBIN_BL31_SHA256": values["DQ08_RKBIN_BL31_SHA256"],
        "DDR_BLOB": preflight.DDR_BLOB,
        "BL31_BLOB": preflight.BL31_BLOB,
        "SELECTED_CONFIGURATION": "cli_minimal",
        "IMAGE_FILE_ID": "Vontar-dq08_bookworm_current_6.18.y_minimal",
        "KERNELSOURCE": "https://git.kernel.org/stable/linux.git",
        "LINUXSOURCEDIR": "linux-kernel",
        "BOOTSOURCE": "https://github.com/u-boot/u-boot.git",
        "BOOTSOURCEDIR": "u-boot",
        "UBOOT_TARGET_MAP": f"BL31=/cache/{preflight.BL31_BLOB} ROCKCHIP_TPL=/cache/{preflight.DDR_BLOB};;u-boot-rockchip.bin",
        "WANT_ARTIFACT_KERNEL_INPUTS_ARRAY": [
            f'KERNELBRANCH=commit:{values["DQ08_TESTED_KERNEL_COMMIT"]}'
        ],
    }


class PreflightTests(unittest.TestCase):
    def test_parses_only_exact_requested_kernel_ref(self) -> None:
        text = "\n".join(
            (
                f"{'1' * 40}\trefs/heads/linux-6.18.y",
                f"{'2' * 40}\trefs/heads/linux-6.18.y-next",
            )
        )
        self.assertEqual(preflight.parse_kernel_refs(text, "linux-6.18.y"), "1" * 40)
        with self.assertRaises(ReleaseError):
            preflight.parse_kernel_refs("", "linux-6.18.y")

    def test_compile_command_is_fixed_and_never_allows_unsupported(self) -> None:
        values = {
            "DQ08_BOARD": "vontar-dq08",
            "DQ08_MAINTAINER": "fensoft",
            "DQ08_MAINTAINER_EMAIL": "fensoft@users.noreply.github.com",
        }
        command = preflight.config_command(Path("/tmp/armbian"), values, "a" * 40)
        self.assertIn("RELEASE=bookworm", command)
        self.assertIn("BRANCH=current", command)
        self.assertIn("BUILD_MINIMAL=yes", command)
        self.assertIn("BUILD_DESKTOP=no", command)
        self.assertIn("COMPRESS_OUTPUTIMAGE=sha,xz", command)
        self.assertIn("IMAGE_XZ_COMPRESSION_RATIO=1", command)
        self.assertIn(f"KERNELBRANCH=commit:{'a' * 40}", command)
        self.assertNotIn("--allow-unsupported", command)

    def test_config_assertion_requires_exact_kernel_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = make_release_fixture(Path(temporary))
            config = config_fixture(fixture.module_values)
            config["WANT_ARTIFACT_KERNEL_INPUTS_ARRAY"] = [
                f"KERNELBRANCH=commit:{'f' * 40}"
            ]
            with self.assertRaisesRegex(ReleaseError, "exact pinned KERNELBRANCH"):
                preflight.assert_config(
                    config,
                    fixture.module_values,
                    fixture.preflight["kernel"]["commit"],
                )

    def test_kernel_series_mismatch_is_machine_readable_exit_three(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = make_release_fixture(Path(temporary))
            family = fixture.armbian / "config/sources/families/include/rockchip64_common.inc"
            family.parent.mkdir(parents=True)
            family.write_text('current)\n  declare -g KERNEL_MAJOR_MINOR="6.19"\n  ;;\n', encoding="utf-8")
            output = fixture.root / "incompatible.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPOSITORY_ROOT / "scripts/ci/preflight.py"),
                    "--bsp-root",
                    str(fixture.bsp),
                    "--armbian-root",
                    str(fixture.armbian),
                    "--armbian-tag",
                    "v26.5.1",
                    "--armbian-commit",
                    fixture.preflight["armbian"]["commit"],
                    "--kernel-commit",
                    fixture.preflight["kernel"]["commit"],
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 3, result.stderr)
            payload = json.loads(output.read_text())
            self.assertEqual(payload["status"], "kernel_port_required")
            self.assertFalse(payload["should_build"])
            self.assertEqual(payload["actual_kernel_series"], "6.19")

    def test_ready_preflight_runs_dry_run_install_verify_and_pins_sha(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = make_release_fixture(Path(temporary))
            family = fixture.armbian / "config/sources/families/include/rockchip64_common.inc"
            family.parent.mkdir(parents=True)
            family.write_text('current)\n  declare -g KERNEL_MAJOR_MINOR="6.18"\n  ;;\n', encoding="utf-8")
            calls = fixture.root / "calls.jsonl"
            recorder = (
                "#!/usr/bin/env python3\n"
                "import json, pathlib, sys\n"
                f"p=pathlib.Path({str(calls)!r})\n"
                "with p.open('a') as h: h.write(json.dumps(sys.argv)+\"\\n\")\n"
            )
            make_executable(fixture.bsp / "verify.sh", recorder)
            make_executable(fixture.bsp / "install.sh", recorder)
            config = config_fixture(fixture.module_values)
            compile_script = (
                "#!/usr/bin/env python3\n"
                "import json, pathlib, sys\n"
                f"p=pathlib.Path({str(calls)!r})\n"
                "with p.open('a') as h: h.write(json.dumps(sys.argv)+\"\\n\")\n"
                f"print({json.dumps(json.dumps(config))})\n"
            )
            make_executable(fixture.armbian / "compile.sh", compile_script)
            refs = fixture.root / "refs.txt"
            refs.write_text(
                f'{fixture.preflight["kernel"]["commit"]}\trefs/heads/linux-6.18.y\n',
                encoding="utf-8",
            )
            output = fixture.root / "ready.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPOSITORY_ROOT / "scripts/ci/preflight.py"),
                    "--bsp-root",
                    str(fixture.bsp),
                    "--armbian-root",
                    str(fixture.armbian),
                    "--armbian-tag",
                    "v26.5.1",
                    "--armbian-commit",
                    fixture.preflight["armbian"]["commit"],
                    "--kernel-refs",
                    str(refs),
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output.read_text())
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["kernel"]["commit"], fixture.preflight["kernel"]["commit"])
            invocations = [json.loads(line) for line in calls.read_text().splitlines()]
            flattened = [argument for invocation in invocations for argument in invocation]
            self.assertIn("--dry-run", flattened)
            self.assertIn(f'KERNELBRANCH=commit:{fixture.preflight["kernel"]["commit"]}', flattened)
            self.assertNotIn("--allow-unsupported", flattened)


if __name__ == "__main__":
    unittest.main()
