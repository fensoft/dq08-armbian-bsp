#!/usr/bin/env python3
"""Build a pinned DQ08 image, stage its three assets, and write its manifest."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from _lib import (
    ReleaseError,
    dump_json,
    git_commit,
    load_json,
    parse_module_conf,
    require,
    require_sha1,
    run,
)
from create_manifest import MANIFEST_NAME, validate_preflight


def snapshot_images(directory: Path) -> dict[Path, tuple[int, int]]:
    if not directory.exists():
        return {}
    return {
        path.resolve(): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in directory.glob("*.img.xz")
        if path.is_file() and not path.is_symlink()
    }


def fixed_compile_args(module: dict[str, str], kernel_commit: str) -> list[str]:
    return [
        f'BOARD={module["DQ08_BOARD"]}',
        "BRANCH=current",
        "RELEASE=bookworm",
        "BUILD_MINIMAL=yes",
        "BUILD_DESKTOP=no",
        "KERNEL_CONFIGURE=no",
        f'MAINTAINER={module["DQ08_MAINTAINER"]}',
        f'MAINTAINERMAIL={module["DQ08_MAINTAINER_EMAIL"]}',
        f"KERNELBRANCH=commit:{kernel_commit}",
        "PREFER_DOCKER=yes",
    ]


def build_commands(
    bsp_root: Path,
    armbian_root: Path,
    module: dict[str, str],
    kernel_commit: str,
) -> tuple[list[str], list[str], list[str]]:
    common = fixed_compile_args(module, kernel_commit)
    compile_script = armbian_root / "compile.sh"
    kernel = [
        str(compile_script),
        "kernel",
        *common,
        "ARTIFACT_IGNORE_CACHE=yes",
        "CLEAN_LEVEL=make-kernel",
    ]
    uboot = [
        str(compile_script),
        "uboot",
        *common,
        "ARTIFACT_IGNORE_CACHE=yes",
        "CLEAN_LEVEL=make-uboot",
    ]
    image = [
        str(bsp_root / "build.sh"),
        str(armbian_root),
        "bookworm",
        f"KERNELBRANCH=commit:{kernel_commit}",
        "COMPRESS_OUTPUTIMAGE=sha,xz",
        "IMAGE_XZ_COMPRESSION_RATIO=1",
    ]
    return kernel, uboot, image


def compare_builder_preflight(expected: dict[str, Any], actual: dict[str, Any]) -> None:
    for key in ("release_name", "armbian", "bsp", "kernel", "uboot", "rkbin", "maintainer", "build"):
        require(actual.get(key) == expected.get(key), f"Builder preflight changed {key} from the hosted preflight")


def stage_new_image(
    output_images: Path, before: dict[Path, tuple[int, int]], stage_dir: Path
) -> tuple[Path, Path, Path]:
    require(not stage_dir.exists() or stage_dir.is_dir(), f"Stage path is not a directory: {stage_dir}")
    require(not stage_dir.is_symlink(), f"Stage directory must not be a symlink: {stage_dir}")
    stage_dir.mkdir(parents=True, exist_ok=True)
    require(not any(stage_dir.iterdir()), f"Stage directory must be empty: {stage_dir}")
    after = snapshot_images(output_images)
    changed = [path for path, stat in after.items() if before.get(path) != stat]
    require(len(changed) == 1, f"Build must produce exactly one new or changed .img.xz, found {len(changed)}")
    image = changed[0]
    checksum = Path(f"{image}.sha")
    metadata = Path(f"{str(image).removesuffix('.xz')}.txt")
    for source in (image, checksum, metadata):
        require(source.is_file() and not source.is_symlink(), f"Build output is missing a regular file: {source}")
    staged = tuple(stage_dir / source.name for source in (image, checksum, metadata))
    for source, destination in zip((image, checksum, metadata), staged, strict=True):
        shutil.copy2(source, destination)
    return staged  # type: ignore[return-value]


def build_release(args: argparse.Namespace) -> dict[str, Any]:
    bsp_root = args.bsp_root.resolve()
    armbian_root = args.armbian_root.resolve()
    stage_dir = args.stage_dir.resolve()
    module = parse_module_conf(bsp_root / "module.conf")
    expected = load_json(args.preflight.resolve())
    require(isinstance(expected, dict), "Preflight JSON must be an object")
    validate_preflight(expected, module)
    require(git_commit(armbian_root) == expected["armbian"]["commit"], "Armbian builder checkout differs from preflight")
    require(git_commit(bsp_root) == expected["bsp"]["commit"], "BSP builder checkout differs from preflight")
    kernel_commit = require_sha1(expected["kernel"]["commit"], "preflight kernel commit")

    with tempfile.TemporaryDirectory(prefix="dq08-builder-preflight-") as temporary:
        builder_preflight = Path(temporary) / "preflight.json"
        run(
            [
                sys.executable,
                str(bsp_root / "scripts/ci/preflight.py"),
                "--bsp-root",
                str(bsp_root),
                "--armbian-root",
                str(armbian_root),
                "--armbian-tag",
                expected["armbian"]["tag"],
                "--armbian-commit",
                expected["armbian"]["commit"],
                "--kernel-commit",
                kernel_commit,
                "--output",
                str(builder_preflight),
            ],
            cwd=bsp_root,
        )
        actual = load_json(builder_preflight)
        require(isinstance(actual, dict), "Builder preflight JSON must be an object")
        compare_builder_preflight(expected, actual)

    output_images = armbian_root / "output/images"
    before = snapshot_images(output_images)
    kernel_command, uboot_command, image_command = build_commands(
        bsp_root, armbian_root, module, kernel_commit
    )
    run(kernel_command, cwd=armbian_root, attempts=args.build_attempts)
    run(uboot_command, cwd=armbian_root, attempts=args.build_attempts)
    run(image_command, cwd=bsp_root, attempts=args.build_attempts)
    staged = stage_new_image(output_images, before, stage_dir)

    manifest_path = stage_dir / MANIFEST_NAME
    manifest_command = [
        sys.executable,
        str(bsp_root / "scripts/ci/create_manifest.py"),
        "--bsp-root",
        str(bsp_root),
        "--armbian-root",
        str(armbian_root),
        "--preflight",
        str(args.preflight.resolve()),
        "--stage-dir",
        str(stage_dir),
        "--workflow-run-id",
        args.workflow_run_id,
        "--output",
        str(manifest_path),
    ]
    if args.workflow_run_attempt is not None:
        manifest_command.extend(("--workflow-run-attempt", str(args.workflow_run_attempt)))
    if args.workflow_run_url is not None:
        manifest_command.extend(("--workflow-run-url", args.workflow_run_url))
    run(manifest_command, cwd=bsp_root, capture=True)
    require(manifest_path.is_file(), "Manifest creator did not produce build-manifest.json")

    return {
        "schema_version": 1,
        "status": "staged",
        "release_name": expected["release_name"],
        "stage_dir": str(stage_dir),
        "manifest": str(manifest_path),
        "assets": [path.name for path in (*staged, manifest_path)],
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
    result.add_argument("--build-attempts", type=int, choices=range(1, 4), default=3)
    result.add_argument("--output", type=Path, help="optional build-result JSON (outside the stage directory)")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.output is not None:
            stage = args.stage_dir.resolve()
            output = args.output.resolve()
            require(output.parent != stage, "Build-result JSON must be outside the four-file stage directory")
        result = build_release(args)
        rendered = dump_json(result, args.output)
        sys.stdout.write(rendered)
        return 0
    except (OSError, ReleaseError) as exc:
        print(f"build_release: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
