#!/usr/bin/env python3
"""Verify builder-side source pins and create the DQ08 build manifest."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from _lib import (
    ReleaseError,
    dump_json,
    git_commit,
    load_json,
    parse_module_conf,
    reject_placeholder,
    release_name,
    require,
    require_sha1,
    require_sha256,
    sha256_file,
)


MANIFEST_NAME = "build-manifest.json"


def require_object(value: Any, label: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def parse_checksum(path: Path, expected_name: str) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ReleaseError(f"Checksum file does not exist: {path}") from exc
    require(len(lines) == 1, f"Checksum file must contain exactly one line: {path.name}")
    match = re.fullmatch(r"([0-9a-f]{64})[ \t]+\*?([^/\s]+)", lines[0])
    require(match is not None, f"Malformed SHA-256 file: {path.name}")
    digest, filename = match.groups()  # type: ignore[union-attr]
    require(filename == expected_name, f"Checksum names {filename!r}, expected {expected_name!r}")
    return require_sha256(digest, f"checksum in {path.name}")


def parse_image_metadata(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([A-Za-z][A-Za-z ]*[A-Za-z]):\s+(.*)", line)
        if match:
            values[match.group(1).strip().lower().replace(" ", "_")] = match.group(2).strip()
    required = ("revision", "board", "kernel", "sources_rev", "maintainer")
    missing = [key for key in required if not values.get(key)]
    require(not missing, f"Image metadata is missing: {', '.join(missing)}")
    return values


def stage_assets(stage_dir: Path) -> tuple[Path, Path, Path]:
    require(stage_dir.is_dir(), f"Stage directory does not exist: {stage_dir}")
    require(not stage_dir.is_symlink(), f"Stage directory must not be a symlink: {stage_dir}")
    entries = list(stage_dir.iterdir())
    require(all(item.is_file() and not item.is_symlink() for item in entries), "Stage entries must be regular, non-symlink files")
    require(not (stage_dir / MANIFEST_NAME).exists(), f"Refusing to replace existing {MANIFEST_NAME}")
    images = [item for item in entries if item.name.endswith(".img.xz")]
    require(len(images) == 1, f"Stage must contain exactly one .img.xz before manifest creation, found {len(images)}")
    image = images[0]
    checksum = stage_dir / f"{image.name}.sha"
    metadata = stage_dir / f"{image.name.removesuffix('.xz')}.txt"
    require(checksum in entries, f"Missing staged checksum: {checksum.name}")
    require(metadata in entries, f"Missing staged metadata: {metadata.name}")
    require(set(entries) == {image, checksum, metadata}, "Stage must contain only image, checksum, and metadata before manifest creation")
    return image, checksum, metadata


def verify_source_checkout(path: Path, expected: str, label: str) -> None:
    require(path.is_dir(), f"{label} source directory does not exist: {path}")
    actual = git_commit(path)
    require(actual == expected, f"{label} source is {actual}, expected {expected}")


def validate_preflight(preflight: dict[str, Any], module: dict[str, str]) -> None:
    require(preflight.get("schema_version") == 1, "Unsupported preflight schema_version")
    require(preflight.get("status") == "ready" and preflight.get("should_build") is True, "Preflight is not ready")
    armbian = require_object(preflight.get("armbian"), "preflight armbian")
    bsp = require_object(preflight.get("bsp"), "preflight bsp")
    kernel = require_object(preflight.get("kernel"), "preflight kernel")
    uboot = require_object(preflight.get("uboot"), "preflight uboot")
    rkbin = require_object(preflight.get("rkbin"), "preflight rkbin")
    build = require_object(preflight.get("build"), "preflight build")
    maintainer = require_object(preflight.get("maintainer"), "preflight maintainer")

    require_sha1(str(armbian.get("commit", "")), "preflight Armbian commit")
    require_sha1(str(bsp.get("commit", "")), "preflight BSP commit")
    require_sha1(str(kernel.get("commit", "")), "preflight kernel commit")
    require(uboot.get("commit") == module["DQ08_UBOOT_COMMIT"], "Preflight U-Boot commit differs from module.conf")
    require(rkbin.get("commit") == module["DQ08_RKBIN_COMMIT"], "Preflight rkbin commit differs from module.conf")
    require(bsp.get("version") == module["DQ08_MODULE_VERSION"], "Preflight BSP version differs from module.conf")
    require(kernel.get("series") == module["DQ08_KERNEL_SERIES"], "Preflight kernel series differs from module.conf")
    require(
        preflight.get("release_name") == release_name(str(armbian.get("tag")), module["DQ08_MODULE_VERSION"]),
        "Preflight release name is inconsistent",
    )
    require(
        build == {
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
        "Preflight build settings are not the fixed DQ08 release settings",
    )
    require(maintainer.get("name") == module["DQ08_MAINTAINER"], "Preflight maintainer name differs from module.conf")
    require(maintainer.get("email") == module["DQ08_MAINTAINER_EMAIL"], "Preflight maintainer email differs from module.conf")


def create_manifest(args: argparse.Namespace) -> dict[str, Any]:
    bsp_root = args.bsp_root.resolve()
    armbian_root = args.armbian_root.resolve()
    stage_dir = args.stage_dir.resolve()
    module = parse_module_conf(bsp_root / "module.conf")
    preflight = load_json(args.preflight.resolve())
    require(isinstance(preflight, dict), "Preflight JSON must be an object")
    validate_preflight(preflight, module)
    image, checksum_file, metadata_file = stage_assets(stage_dir)

    armbian = preflight["armbian"]
    bsp = preflight["bsp"]
    kernel = preflight["kernel"]
    uboot = preflight["uboot"]
    rkbin = preflight["rkbin"]
    expected_image_sha = parse_checksum(checksum_file, image.name)
    actual_image_sha = sha256_file(image)
    require(actual_image_sha == expected_image_sha, "Staged image does not match its SHA-256 file")

    require(git_commit(armbian_root) == armbian["commit"], "Builder Armbian checkout differs from preflight")
    require(git_commit(bsp_root) == bsp["commit"], "Builder BSP checkout differs from preflight")
    kernel_source_dir = kernel.get("source_directory")
    uboot_source_dir = uboot.get("source_directory")
    require(isinstance(kernel_source_dir, str) and kernel_source_dir, "Preflight has no kernel source_directory")
    require(isinstance(uboot_source_dir, str) and uboot_source_dir, "Preflight has no U-Boot source_directory")
    sources_root = armbian_root / "cache/sources"
    verify_source_checkout(sources_root / kernel_source_dir, kernel["commit"], "kernel")
    verify_source_checkout(sources_root / uboot_source_dir, uboot["commit"], "U-Boot")
    rkbin_root = sources_root / rkbin["source_directory"]
    verify_source_checkout(rkbin_root, rkbin["commit"], "rkbin")
    for component in ("ddr", "bl31"):
        details = require_object(rkbin.get(component), f"preflight rkbin {component}")
        relative = details.get("path")
        expected = details.get("sha256")
        require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), f"Invalid rkbin {component} path")
        require(".." not in Path(relative).parts, f"Unsafe rkbin {component} path")
        require(isinstance(expected, str), f"Missing rkbin {component} checksum")
        require(sha256_file(rkbin_root / relative) == expected, f"rkbin {component} blob checksum mismatch")

    metadata = parse_image_metadata(metadata_file)
    require(metadata["board"] == "Vontar-dq08", f"Unexpected image board: {metadata['board']}")
    require(metadata["revision"].startswith(armbian["version"]), "Image revision does not match the Armbian release")
    require(metadata["sources_rev"] == armbian["commit"][: len(metadata["sources_rev"])], "Image Sources rev does not match Armbian commit")
    expected_maintainer = f'{module["DQ08_MAINTAINER"]} <{module["DQ08_MAINTAINER_EMAIL"]}>'
    require(metadata["maintainer"] == expected_maintainer, "Image metadata maintainer differs from module.conf")
    reject_placeholder(metadata["maintainer"], "image metadata maintainer")
    kernel_match = re.fullmatch(r"Linux ([0-9]+\.[0-9]+\.[0-9]+) \(current\)", metadata["kernel"])
    require(kernel_match is not None, f"Unexpected image kernel metadata: {metadata['kernel']}")
    kernel_version = kernel_match.group(1)  # type: ignore[union-attr]
    require(kernel_version.startswith(kernel["series"] + "."), "Image kernel is outside the pinned kernel series")
    filename_marker = f"_Vontar-dq08_bookworm_current_{kernel_version}_minimal.img.xz"
    require(image.name.endswith(filename_marker), f"Image filename does not match fixed release settings: {image.name}")

    workflow: dict[str, Any] = {"run_id": args.workflow_run_id}
    if args.workflow_run_attempt is not None:
        workflow["run_attempt"] = args.workflow_run_attempt
    if args.workflow_run_url is not None:
        workflow["run_url"] = args.workflow_run_url

    assets = {
        image.name: {"role": "image", "size_bytes": image.stat().st_size, "sha256": actual_image_sha},
        checksum_file.name: {"role": "checksum", "size_bytes": checksum_file.stat().st_size, "sha256": sha256_file(checksum_file)},
        metadata_file.name: {"role": "metadata", "size_bytes": metadata_file.stat().st_size, "sha256": sha256_file(metadata_file)},
    }
    return {
        "schema_version": 1,
        "release_name": preflight["release_name"],
        "hardware_tested": False,
        "armbian": armbian,
        "bsp": bsp,
        "kernel": {
            "series": kernel["series"],
            "version": kernel_version,
            "branch": kernel["branch"],
            "source": kernel["source"],
            "commit": kernel["commit"],
            "tested_version": kernel["tested_version"],
            "tested_commit": kernel["tested_commit"],
        },
        "uboot": {
            "version": uboot["version"],
            "tag": uboot["tag"],
            "commit": uboot["commit"],
            "source": uboot["source"],
        },
        "rkbin": {
            "commit": rkbin["commit"],
            "ddr": rkbin["ddr"],
            "bl31": rkbin["bl31"],
        },
        "maintainer": preflight["maintainer"],
        "build": {**preflight["build"], "workflow": workflow},
        "image": {
            "filename": image.name,
            "checksum_filename": checksum_file.name,
            "metadata_filename": metadata_file.name,
            "sha256": actual_image_sha,
            "size_bytes": image.stat().st_size,
        },
        "assets": assets,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--bsp-root", type=Path, default=Path.cwd())
    result.add_argument("--armbian-root", type=Path, required=True)
    result.add_argument("--preflight", type=Path, required=True)
    result.add_argument("--stage-dir", type=Path, required=True)
    result.add_argument("--workflow-run-id", required=True)
    result.add_argument("--workflow-run-attempt", type=int)
    result.add_argument("--workflow-run-url")
    result.add_argument("--output", type=Path, help=f"must be STAGE_DIR/{MANIFEST_NAME}; defaults there")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        output = args.output.resolve() if args.output is not None else args.stage_dir.resolve() / MANIFEST_NAME
        require(output == args.stage_dir.resolve() / MANIFEST_NAME, f"Manifest output must be {MANIFEST_NAME} in the stage directory")
        manifest = create_manifest(args)
        rendered = dump_json(manifest, output)
        sys.stdout.write(rendered)
        return 0
    except (OSError, ReleaseError) as exc:
        print(f"create_manifest: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
