from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BUILD_WRAPPER = REPOSITORY_ROOT / "build.sh"
MODULE_CONF = REPOSITORY_ROOT / "module.conf"


class BuildWrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        match = re.search(
            r'^DQ08_MODULE_VERSION="([^"]+)"$',
            MODULE_CONF.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
        if match is None:
            raise AssertionError("DQ08_MODULE_VERSION is missing from module.conf")
        cls.bsp_version = match.group(1)

    def make_module_fixture(self, root: Path, module_version: str) -> Path:
        module = root / "dq08-armbian-bsp"
        module.mkdir()
        wrapper = module / "build.sh"
        wrapper.write_text(
            BUILD_WRAPPER.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        wrapper.chmod(0o755)

        module_conf = re.sub(
            r'^DQ08_MODULE_VERSION="[^"]+"$',
            f'DQ08_MODULE_VERSION="{module_version}"',
            MODULE_CONF.read_text(encoding="utf-8"),
            count=1,
            flags=re.MULTILINE,
        )
        (module / "module.conf").write_text(module_conf, encoding="utf-8")

        install_script = module / "install.sh"
        install_script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        install_script.chmod(0o755)
        return wrapper

    def make_armbian_fixture(
        self, root: Path, armbian_version: str
    ) -> tuple[Path, Path, dict[str, str]]:
        armbian = root / "armbian-build"
        (armbian / "config/boards").mkdir(parents=True)
        family = armbian / "config/sources/families/include/rockchip64_common.inc"
        family.parent.mkdir(parents=True)
        family.write_text(
            'current)\n  declare -g KERNEL_MAJOR_MINOR="6.18"\n  ;;\n',
            encoding="utf-8",
        )
        (armbian / "VERSION").write_text(f"{armbian_version}\n", encoding="utf-8")

        calls = root / "compile-calls.jsonl"
        compile_script = armbian / "compile.sh"
        compile_script.write_text(
            """#!/usr/bin/env python3
import json
import os
import pathlib
import sys

path = pathlib.Path(os.environ["DQ08_BUILD_WRAPPER_CALLS"])
with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
""",
            encoding="utf-8",
        )
        compile_script.chmod(0o755)

        environment = os.environ.copy()
        environment["DQ08_BUILD_WRAPPER_CALLS"] = str(calls)
        environment.pop("IMAGE_VERSION", None)
        return armbian, calls, environment

    def test_derives_image_version_from_armbian_and_bsp_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            armbian_version = "99.88.77-fixture"
            armbian, calls, environment = self.make_armbian_fixture(
                Path(temporary), armbian_version
            )

            result = subprocess.run(
                [
                    str(BUILD_WRAPPER),
                    str(armbian),
                    "bookworm",
                    "DQ08_TEST_ARGUMENT=yes",
                ],
                text=True,
                capture_output=True,
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            invocations = [
                json.loads(line)
                for line in calls.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(invocations), 1)
            arguments = invocations[0]
            self.assertEqual(arguments[0], "build")
            self.assertEqual(
                [item for item in arguments if item.startswith("IMAGE_VERSION=")],
                [f"IMAGE_VERSION={armbian_version}-bsp-v{self.bsp_version}"],
            )
            self.assertIn("DQ08_TEST_ARGUMENT=yes", arguments)

    def test_key_value_in_release_position_uses_default_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            armbian, calls, environment = self.make_armbian_fixture(
                Path(temporary), "99.88.77-fixture"
            )

            result = subprocess.run(
                [str(BUILD_WRAPPER), str(armbian), "DQ08_TEST_ARGUMENT=yes"],
                text=True,
                capture_output=True,
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = json.loads(calls.read_text(encoding="utf-8").strip())
            self.assertIn("RELEASE=bookworm", arguments)
            self.assertIn("DQ08_TEST_ARGUMENT=yes", arguments)

    def test_rejects_caller_image_version_override(self) -> None:
        for command_tail in (
            ("bookworm", "IMAGE_VERSION=caller-controlled"),
            ("bookworm", "IMAGE_VERSION="),
            ("IMAGE_VERSION=caller-controlled",),
            ("IMAGE_VERSION=",),
        ):
            with (
                self.subTest(command_tail=command_tail),
                tempfile.TemporaryDirectory() as temporary,
            ):
                armbian, calls, environment = self.make_armbian_fixture(
                    Path(temporary), "99.88.77-fixture"
                )

                result = subprocess.run(
                    [str(BUILD_WRAPPER), str(armbian), *command_tail],
                    text=True,
                    capture_output=True,
                    env=environment,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("IMAGE_VERSION", result.stderr)
                self.assertFalse(
                    calls.exists(),
                    "compile.sh must not run when IMAGE_VERSION is caller-controlled",
                )

    def test_normalizes_one_leading_v_in_module_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wrapper = self.make_module_fixture(root, "v1.2.3")
            armbian, calls, environment = self.make_armbian_fixture(
                root, "99.88.77-fixture"
            )

            result = subprocess.run(
                [str(wrapper), str(armbian)],
                text=True,
                capture_output=True,
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = json.loads(calls.read_text(encoding="utf-8").strip())
            self.assertIn(
                "IMAGE_VERSION=99.88.77-fixture-bsp-v1.2.3",
                arguments,
            )
            self.assertNotIn(
                "IMAGE_VERSION=99.88.77-fixture-bsp-vv1.2.3",
                arguments,
            )

    def test_rejects_unsafe_module_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wrapper = self.make_module_fixture(root, "1.2.3/unsafe")
            armbian, calls, environment = self.make_armbian_fixture(
                root, "99.88.77-fixture"
            )

            result = subprocess.run(
                [str(wrapper), str(armbian)],
                text=True,
                capture_output=True,
                env=environment,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DQ08_MODULE_VERSION", result.stderr)
            self.assertFalse(
                calls.exists(),
                "compile.sh must not run with an unsafe BSP module version",
            )


if __name__ == "__main__":
    unittest.main()
