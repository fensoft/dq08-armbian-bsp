#!/usr/bin/env python3
"""Validate a DQ08/Armbian pairing and pin its rolling stable kernel branch."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from _lib import (
    ReleaseError,
    STABLE_ARMBIAN_TAG_RE,
    dump_json,
    extract_last_json_object,
    git_commit,
    has_nested_string,
    parse_module_conf,
    reject_placeholder,
    release_name,
    require,
    require_sha1,
    run,
)


DDR_BLOB = "bin/rk35/rk3528_ddr_1056MHz_4BIT_PCB_v1.10.bin"
BL31_BLOB = "bin/rk35/rk3528_bl31_v1.18.elf"


def current_rockchip64_series(armbian_root: Path) -> str:
    path = armbian_root / "config/sources/families/include/rockchip64_common.inc"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ReleaseError(f"Armbian rockchip64 family config is missing: {path}") from exc
    match = re.search(r"(?ms)^\s*current\)\s*$.*?^\s*;;\s*$", text)
    require(match is not None, f"Cannot find the rockchip64 current block in {path}")
    series = re.search(r'KERNEL_MAJOR_MINOR="([0-9]+\.[0-9]+)"', match.group(0))  # type: ignore[union-attr]
    require(series is not None, "rockchip64/current does not declare KERNEL_MAJOR_MINOR")
    return series.group(1)  # type: ignore[union-attr]


def parse_kernel_refs(text: str, branch: str) -> str:
    wanted = f"refs/heads/{branch}"
    matches: list[str] = []
    for raw in text.splitlines():
        fields = raw.split()
        if len(fields) == 2 and fields[1] == wanted:
            matches.append(require_sha1(fields[0], f"commit for {wanted}"))
    require(len(matches) == 1, f"Expected exactly one {wanted} ref, found {len(matches)}")
    return matches[0]


def resolve_kernel_commit(
    source: str,
    branch: str,
    *,
    supplied_commit: str | None,
    refs_file: Path | None,
    attempts: int,
) -> str:
    if supplied_commit is not None:
        return require_sha1(supplied_commit, "kernel commit")
    if refs_file is not None:
        try:
            text = refs_file.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ReleaseError(f"Kernel refs file does not exist: {refs_file}") from exc
    else:
        text = run(
            ["git", "ls-remote", "--exit-code", source, f"refs/heads/{branch}"],
            capture=True,
            attempts=attempts,
        ).stdout
    return parse_kernel_refs(text, branch)


def config_command(
    armbian_root: Path, module: dict[str, str], kernel_commit: str | None
) -> list[str]:
    command = [
        str(armbian_root / "compile.sh"),
        "config-dump",
        f'BOARD={module["DQ08_BOARD"]}',
        "BRANCH=current",
        "RELEASE=bookworm",
        "BUILD_MINIMAL=yes",
        "BUILD_DESKTOP=no",
        "KERNEL_CONFIGURE=no",
        f'MAINTAINER={module["DQ08_MAINTAINER"]}',
        f'MAINTAINERMAIL={module["DQ08_MAINTAINER_EMAIL"]}',
        "COMPRESS_OUTPUTIMAGE=sha,xz",
        "IMAGE_XZ_COMPRESSION_RATIO=1",
        "PREFER_DOCKER=no",
    ]
    if kernel_commit is not None:
        command.append(f"KERNELBRANCH=commit:{kernel_commit}")
    return command


def config_dump(
    armbian_root: Path, module: dict[str, str], kernel_commit: str | None
) -> dict[str, Any]:
    result = run(
        config_command(armbian_root, module, kernel_commit),
        cwd=armbian_root,
        capture=True,
        env={"CONFIG_DEFS_ONLY": "yes"},
    )
    return extract_last_json_object(result.stdout, "Armbian config-dump")


def assert_config(
    config: dict[str, Any], module: dict[str, str], kernel_commit: str
) -> None:
    expected_scalars = {
        "ARCH": "arm64",
        "DISTRIBUTION": "Debian",
        "KERNEL_MAJOR_MINOR": module["DQ08_KERNEL_SERIES"],
        "KERNELPATCHDIR": f'archive/rockchip64-{module["DQ08_KERNEL_SERIES"]}',
        "LINUXFAMILY": "rockchip64",
        "BOOT_FDT_FILE": "rockchip/rk3528-vontar-dq08.dtb",
        "BOARD_MAINTAINER": module["DQ08_MAINTAINER"],
        "BOOTBRANCH": f'commit:{module["DQ08_UBOOT_COMMIT"]}',
        "BOOTPATCHDIR": f'v{module["DQ08_UBOOT_VERSION"]}',
        "DQ08_RKBIN_COMMIT": module["DQ08_RKBIN_COMMIT"],
        "DQ08_RKBIN_DDR_SHA256": module["DQ08_RKBIN_DDR_SHA256"],
        "DQ08_RKBIN_BL31_SHA256": module["DQ08_RKBIN_BL31_SHA256"],
        "DDR_BLOB": DDR_BLOB,
        "BL31_BLOB": BL31_BLOB,
        "SELECTED_CONFIGURATION": "cli_minimal",
    }
    for key, expected in expected_scalars.items():
        require(config.get(key) == expected, f"config-dump {key} is {config.get(key)!r}, expected {expected!r}")
    reject_placeholder(str(config["BOARD_MAINTAINER"]), "config-dump BOARD_MAINTAINER")
    require(
        has_nested_string(config, f"KERNELBRANCH=commit:{kernel_commit}"),
        "config-dump does not retain the exact pinned KERNELBRANCH commit",
    )
    image_file_id = config.get("IMAGE_FILE_ID", "")
    require(
        isinstance(image_file_id, str)
        and image_file_id.startswith("Vontar-dq08_bookworm_current_")
        and image_file_id.endswith("_minimal"),
        f"config-dump IMAGE_FILE_ID does not describe the fixed Bookworm/current/minimal image: {image_file_id!r}",
    )
    target_map = config.get("UBOOT_TARGET_MAP", "")
    require(isinstance(target_map, str), "config-dump UBOOT_TARGET_MAP must be a string")
    require(DDR_BLOB in target_map and BL31_BLOB in target_map, "U-Boot target map does not use both pinned rkbin blobs")


def run_install_checks(bsp_root: Path, armbian_root: Path, install_mode: str) -> None:
    verify = bsp_root / "verify.sh"
    install = bsp_root / "install.sh"
    run([str(verify)], cwd=bsp_root)
    run([str(install), "--dry-run", str(armbian_root)], cwd=bsp_root)
    if install_mode == "install":
        run([str(install), str(armbian_root)], cwd=bsp_root)
    run([str(verify), str(armbian_root)], cwd=bsp_root)


def preflight(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    bsp_root = args.bsp_root.resolve()
    armbian_root = args.armbian_root.resolve()
    module = parse_module_conf(bsp_root / "module.conf")
    require(
        STABLE_ARMBIAN_TAG_RE.fullmatch(args.armbian_tag) is not None,
        f"Armbian tag is not a stable point release: {args.armbian_tag}",
    )
    expected_armbian_commit = require_sha1(args.armbian_commit, "Armbian commit")
    actual_armbian_commit = git_commit(armbian_root)
    require(
        actual_armbian_commit == expected_armbian_commit,
        f"Armbian checkout is {actual_armbian_commit}, expected {expected_armbian_commit}",
    )
    bsp_commit = git_commit(bsp_root)

    actual_series = current_rockchip64_series(armbian_root)
    expected_series = module["DQ08_KERNEL_SERIES"]
    if actual_series != expected_series:
        result = {
            "schema_version": 1,
            "status": "kernel_port_required",
            "should_build": False,
            "armbian_tag": args.armbian_tag,
            "armbian_commit": actual_armbian_commit,
            "expected_kernel_series": expected_series,
            "actual_kernel_series": actual_series,
            "release_name": release_name(args.armbian_tag, module["DQ08_MODULE_VERSION"]),
        }
        return result, 3

    run_install_checks(bsp_root, armbian_root, args.install_mode)
    rolling = config_dump(armbian_root, module, None)
    require(
        rolling.get("KERNEL_MAJOR_MINOR") == expected_series,
        "rolling config-dump disagrees with the rockchip64 current series",
    )
    source = rolling.get("KERNELSOURCE")
    require(isinstance(source, str) and source.startswith(("https://", "http://")), "config-dump KERNELSOURCE is not an HTTP(S) repository")
    branch = f"linux-{expected_series}.y"
    rolling_image_id = rolling.get("IMAGE_FILE_ID", "")
    require(
        isinstance(rolling_image_id, str)
        and f"_current_{expected_series}.y_" in rolling_image_id,
        f"rockchip64/current does not describe rolling series {expected_series}.y",
    )
    kernel_commit = resolve_kernel_commit(
        source,
        branch,
        supplied_commit=args.kernel_commit,
        refs_file=args.kernel_refs,
        attempts=args.fetch_attempts,
    )
    pinned = config_dump(armbian_root, module, kernel_commit)
    assert_config(pinned, module, kernel_commit)

    result = {
        "schema_version": 1,
        "status": "ready",
        "should_build": True,
        "release_name": release_name(args.armbian_tag, module["DQ08_MODULE_VERSION"]),
        "armbian": {
            "tag": args.armbian_tag,
            "version": args.armbian_tag.removeprefix("v"),
            "commit": actual_armbian_commit,
        },
        "bsp": {
            "version": module["DQ08_MODULE_VERSION"],
            "commit": bsp_commit,
            "source_bsp_commit": module["DQ08_SOURCE_BSP_COMMIT"],
        },
        "kernel": {
            "series": expected_series,
            "branch": branch,
            "source": source,
            "commit": kernel_commit,
            "tested_version": module["DQ08_TESTED_KERNEL"],
            "tested_commit": module["DQ08_TESTED_KERNEL_COMMIT"],
            "source_directory": pinned.get("LINUXSOURCEDIR"),
        },
        "uboot": {
            "version": module["DQ08_UBOOT_VERSION"],
            "tag": f'v{module["DQ08_UBOOT_VERSION"]}',
            "commit": module["DQ08_UBOOT_COMMIT"],
            "source": pinned.get("BOOTSOURCE"),
            "source_directory": pinned.get("BOOTSOURCEDIR"),
        },
        "rkbin": {
            "commit": module["DQ08_RKBIN_COMMIT"],
            "source_directory": "vontar-dq08-rkbin",
            "ddr": {"path": DDR_BLOB, "sha256": module["DQ08_RKBIN_DDR_SHA256"]},
            "bl31": {"path": BL31_BLOB, "sha256": module["DQ08_RKBIN_BL31_SHA256"]},
        },
        "maintainer": {
            "name": module["DQ08_MAINTAINER"],
            "email": module["DQ08_MAINTAINER_EMAIL"],
        },
        "build": {
            "board": module["DQ08_BOARD"],
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
    return result, 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--bsp-root", type=Path, default=Path.cwd())
    result.add_argument("--armbian-root", type=Path, required=True)
    result.add_argument("--armbian-tag", required=True)
    result.add_argument("--armbian-commit", required=True)
    source = result.add_mutually_exclusive_group()
    source.add_argument("--kernel-commit", help="already-resolved exact kernel SHA")
    source.add_argument("--kernel-refs", type=Path, help="offline git-ls-remote output fixture")
    result.add_argument("--install-mode", choices=("install", "already-installed"), default="install")
    result.add_argument("--fetch-attempts", type=int, choices=range(1, 4), default=3)
    result.add_argument("--output", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result, status = preflight(args)
        rendered = dump_json(result, args.output)
        sys.stdout.write(rendered)
        return status
    except ReleaseError as exc:
        print(f"preflight: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
