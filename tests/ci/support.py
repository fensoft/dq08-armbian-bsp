"""Test fixtures for the dependency-free CI helpers."""

from __future__ import annotations

import hashlib
import json
import lzma
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPOSITORY_ROOT / "scripts/ci"


def run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)


def init_repo(path: Path, files: dict[str, bytes | str] | None = None) -> str:
    path.mkdir(parents=True, exist_ok=True)
    for relative, content in (files or {}).items():
        destination = path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            destination.write_bytes(content)
        else:
            destination.write_text(content, encoding="utf-8")
    run(["git", "init", "-q", "-b", "main"], path)
    run(["git", "config", "user.name", "CI Test"], path)
    run(["git", "config", "user.email", "ci@example.invalid"], path)
    run(["git", "add", "."], path)
    run(["git", "commit", "-q", "-m", "fixture"], path)
    return run(["git", "rev-parse", "HEAD"], path).stdout.strip()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def module_conf(values: dict[str, str]) -> str:
    ordered = (
        "DQ08_MODULE_VERSION",
        "DQ08_BOARD",
        "DQ08_KERNEL_SERIES",
        "DQ08_TESTED_KERNEL",
        "DQ08_TESTED_KERNEL_COMMIT",
        "DQ08_UBOOT_VERSION",
        "DQ08_UBOOT_COMMIT",
        "DQ08_TESTED_ARMBIAN_COMMIT",
        "DQ08_SOURCE_BSP_COMMIT",
        "DQ08_RKBIN_COMMIT",
        "DQ08_RKBIN_DDR_SHA256",
        "DQ08_RKBIN_BL31_SHA256",
        "DQ08_MAINTAINER",
        "DQ08_MAINTAINER_EMAIL",
    )
    return "".join(f'{key}="{values[key]}"\n' for key in ordered)


def make_release_fixture(root: Path) -> SimpleNamespace:
    ddr_data = b"test ddr firmware\n"
    bl31_data = b"test bl31 firmware\n"
    armbian = root / "armbian"
    armbian_commit = init_repo(armbian, {"README": "Armbian fixture\n"})
    kernel_dir = armbian / "cache/sources/linux-kernel"
    kernel_commit = init_repo(kernel_dir, {"README": "kernel\n"})
    uboot_dir = armbian / "cache/sources/u-boot"
    uboot_commit = init_repo(uboot_dir, {"README": "u-boot\n"})
    rkbin_dir = armbian / "cache/sources/vontar-dq08-rkbin"
    ddr_path = "bin/rk35/rk3528_ddr_1056MHz_4BIT_PCB_v1.10.bin"
    bl31_path = "bin/rk35/rk3528_bl31_v1.18.elf"
    rkbin_commit = init_repo(rkbin_dir, {ddr_path: ddr_data, bl31_path: bl31_data})

    values = {
        "DQ08_MODULE_VERSION": "1.2.3",
        "DQ08_BOARD": "vontar-dq08",
        "DQ08_KERNEL_SERIES": "6.18",
        "DQ08_TESTED_KERNEL": "6.18.39",
        "DQ08_TESTED_KERNEL_COMMIT": kernel_commit,
        "DQ08_UBOOT_VERSION": "2026.04",
        "DQ08_UBOOT_COMMIT": uboot_commit,
        "DQ08_TESTED_ARMBIAN_COMMIT": armbian_commit,
        "DQ08_SOURCE_BSP_COMMIT": "d" * 40,
        "DQ08_RKBIN_COMMIT": rkbin_commit,
        "DQ08_RKBIN_DDR_SHA256": sha256(ddr_data),
        "DQ08_RKBIN_BL31_SHA256": sha256(bl31_data),
        "DQ08_MAINTAINER": "fensoft",
        "DQ08_MAINTAINER_EMAIL": "fensoft@gmail.com",
    }
    bsp = root / "bsp"
    bsp_commit = init_repo(bsp, {"module.conf": module_conf(values)})
    preflight: dict[str, Any] = {
        "schema_version": 1,
        "status": "ready",
        "should_build": True,
        "release_name": "dq08-armbian-v26.5.1-bsp-v1.2.3",
        "armbian": {"tag": "v26.5.1", "version": "26.5.1", "commit": armbian_commit},
        "bsp": {"version": "1.2.3", "commit": bsp_commit, "source_bsp_commit": "d" * 40},
        "kernel": {
            "series": "6.18",
            "branch": "linux-6.18.y",
            "source": "https://git.kernel.org/stable/linux.git",
            "commit": kernel_commit,
            "tested_version": "6.18.39",
            "tested_commit": kernel_commit,
            "source_directory": "linux-kernel",
        },
        "uboot": {
            "version": "2026.04",
            "tag": "v2026.04",
            "commit": uboot_commit,
            "source": "https://github.com/u-boot/u-boot.git",
            "source_directory": "u-boot",
        },
        "rkbin": {
            "commit": rkbin_commit,
            "source_directory": "vontar-dq08-rkbin",
            "ddr": {"path": ddr_path, "sha256": sha256(ddr_data)},
            "bl31": {"path": bl31_path, "sha256": sha256(bl31_data)},
        },
        "maintainer": {"name": "fensoft", "email": "fensoft@gmail.com"},
        "build": {
            "board": "vontar-dq08",
            "branch": "current",
            "distribution": "Debian",
            "release": "bookworm",
            "minimal": True,
            "desktop": False,
            "compression": "xz",
            "xz_level": 1,
            "checksum": "sha256",
        },
    }
    preflight_path = root / "preflight.json"
    preflight_path.write_text(json.dumps(preflight), encoding="utf-8")
    stage = root / "stage"
    stage.mkdir()
    image_name = "Armbian_26.5.1_Vontar-dq08_bookworm_current_6.18.40_minimal.img.xz"
    image = stage / image_name
    image.write_bytes(lzma.compress(b"DQ08 image fixture\n", preset=1))
    image_sha = hashlib.sha256(image.read_bytes()).hexdigest()
    (stage / f"{image_name}.sha").write_text(f"{image_sha}  {image_name}\n", encoding="utf-8")
    metadata_name = image_name.removesuffix(".xz") + ".txt"
    (stage / metadata_name).write_text(
        "\n".join(
            (
                "Generated with Armbian build framework",
                "Revision:       26.5.1",
                "Board:          Vontar-dq08",
                "Kernel:         Linux 6.18.40 (current)",
                f"Sources rev:    {armbian_commit[:10]}",
                "Maintainer:     fensoft <fensoft@gmail.com>",
                "",
            )
        ),
        encoding="utf-8",
    )
    return SimpleNamespace(
        root=root,
        bsp=bsp,
        armbian=armbian,
        stage=stage,
        preflight=preflight,
        preflight_path=preflight_path,
        module_values=values,
        image=image,
    )


def make_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
