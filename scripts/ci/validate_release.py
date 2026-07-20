#!/usr/bin/env python3
"""Perform hosted validation of the four staged DQ08 GitHub release assets."""

from __future__ import annotations

import argparse
import copy
import re
import sys
from pathlib import Path
from typing import Any

from _lib import (
    ReleaseError,
    dump_json,
    load_json,
    parse_module_conf,
    reject_placeholder,
    release_name,
    require,
    require_sha1,
    require_sha256,
    run,
    sha256_file,
)
from create_manifest import MANIFEST_NAME, parse_checksum, parse_image_metadata


GITHUB_ASSET_LIMIT = 2 * 1024 * 1024 * 1024


class ConflictError(ReleaseError):
    """An immutable release exists with different provenance or bytes."""


def object_value(value: Any, label: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def exact_stage_entries(stage_dir: Path) -> tuple[Path, Path, Path, Path]:
    require(stage_dir.is_dir() and not stage_dir.is_symlink(), f"Invalid stage directory: {stage_dir}")
    entries = list(stage_dir.iterdir())
    require(all(path.is_file() and not path.is_symlink() for path in entries), "All release assets must be regular, non-symlink files")
    require(len(entries) == 4, f"Release must contain exactly four assets, found {len(entries)}")
    manifests = [path for path in entries if path.name == MANIFEST_NAME]
    images = [path for path in entries if path.name.endswith(".img.xz")]
    require(len(manifests) == 1, f"Release must contain exactly one {MANIFEST_NAME}")
    require(len(images) == 1, "Release must contain exactly one .img.xz")
    image = images[0]
    checksum = stage_dir / f"{image.name}.sha"
    metadata = stage_dir / f"{image.name.removesuffix('.xz')}.txt"
    require(set(entries) == {image, checksum, metadata, manifests[0]}, "Release asset names do not form one image/xz checksum/metadata/manifest set")
    for path in entries:
        require(path.stat().st_size < GITHUB_ASSET_LIMIT, f"Asset is not below GitHub's 2 GiB limit: {path.name}")
    return image, checksum, metadata, manifests[0]


def validate_manifest_policy(manifest: dict[str, Any], module: dict[str, str]) -> None:
    require(manifest.get("schema_version") == 1, "Unsupported build manifest schema_version")
    require(manifest.get("hardware_tested") is False, "Automated release must explicitly set hardware_tested to false")
    armbian = object_value(manifest.get("armbian"), "manifest armbian")
    bsp = object_value(manifest.get("bsp"), "manifest bsp")
    kernel = object_value(manifest.get("kernel"), "manifest kernel")
    uboot = object_value(manifest.get("uboot"), "manifest uboot")
    rkbin = object_value(manifest.get("rkbin"), "manifest rkbin")
    maintainer = object_value(manifest.get("maintainer"), "manifest maintainer")
    build = object_value(manifest.get("build"), "manifest build")
    workflow = object_value(build.get("workflow"), "manifest build.workflow")
    image = object_value(manifest.get("image"), "manifest image")
    assets = object_value(manifest.get("assets"), "manifest assets")

    armbian_tag = armbian.get("tag")
    require(isinstance(armbian_tag, str), "Manifest Armbian tag is missing")
    require(manifest.get("release_name") == release_name(armbian_tag, module["DQ08_MODULE_VERSION"]), "Manifest release_name is inconsistent")
    require(armbian.get("version") == armbian_tag.removeprefix("v"), "Manifest Armbian version/tag mismatch")
    require_sha1(str(armbian.get("commit", "")), "manifest Armbian commit")
    require(bsp.get("version") == module["DQ08_MODULE_VERSION"], "Manifest BSP version differs from module.conf")
    require_sha1(str(bsp.get("commit", "")), "manifest BSP commit")
    require(bsp.get("source_bsp_commit") == module["DQ08_SOURCE_BSP_COMMIT"], "Manifest source BSP commit differs from module.conf")

    require(kernel.get("series") == module["DQ08_KERNEL_SERIES"], "Manifest kernel series differs from module.conf")
    require(isinstance(kernel.get("version"), str) and kernel["version"].startswith(kernel["series"] + "."), "Manifest kernel version is outside its series")
    require(kernel.get("branch") == f'linux-{module["DQ08_KERNEL_SERIES"]}.y', "Manifest rolling kernel branch is wrong")
    require_sha1(str(kernel.get("commit", "")), "manifest kernel commit")
    require(kernel.get("tested_version") == module["DQ08_TESTED_KERNEL"], "Manifest tested kernel version differs from module.conf")
    require(kernel.get("tested_commit") == module["DQ08_TESTED_KERNEL_COMMIT"], "Manifest tested kernel commit differs from module.conf")
    require(isinstance(kernel.get("source"), str) and kernel["source"].startswith(("http://", "https://")), "Manifest kernel source is invalid")

    require(uboot.get("version") == module["DQ08_UBOOT_VERSION"], "Manifest U-Boot version differs from module.conf")
    require(uboot.get("tag") == f'v{module["DQ08_UBOOT_VERSION"]}', "Manifest U-Boot tag differs from module.conf")
    require(uboot.get("commit") == module["DQ08_UBOOT_COMMIT"], "Manifest U-Boot commit differs from module.conf")
    require(rkbin.get("commit") == module["DQ08_RKBIN_COMMIT"], "Manifest rkbin commit differs from module.conf")
    for component, checksum_key in (("ddr", "DQ08_RKBIN_DDR_SHA256"), ("bl31", "DQ08_RKBIN_BL31_SHA256")):
        details = object_value(rkbin.get(component), f"manifest rkbin {component}")
        require(details.get("sha256") == module[checksum_key], f"Manifest rkbin {component} hash differs from module.conf")
        require_sha256(str(details.get("sha256", "")), f"manifest rkbin {component} hash")
        relative = details.get("path")
        require(isinstance(relative, str) and relative.startswith("bin/rk35/"), f"Manifest rkbin {component} path is invalid")

    require(maintainer == {"name": module["DQ08_MAINTAINER"], "email": module["DQ08_MAINTAINER_EMAIL"]}, "Manifest maintainer differs from module.conf")
    reject_placeholder(f'{maintainer["name"]} <{maintainer["email"]}>', "manifest maintainer")
    expected_build = {
        "board": module["DQ08_BOARD"],
        "branch": "current",
        "distribution": "Debian",
        "release": "bookworm",
        "minimal": True,
        "desktop": False,
        "compression": "xz",
        "xz_level": 1,
        "checksum": "sha256",
    }
    require({key: build.get(key) for key in expected_build} == expected_build, "Manifest build policy is not Bookworm/current/minimal/xz-1")
    require(isinstance(workflow.get("run_id"), str) and workflow["run_id"], "Manifest workflow run_id is missing")
    require_sha256(str(image.get("sha256", "")), "manifest image checksum")
    require(isinstance(image.get("size_bytes"), int) and 0 < image["size_bytes"] < GITHUB_ASSET_LIMIT, "Manifest image size is invalid")
    require(len(assets) == 3, "Manifest assets map must describe the three non-manifest assets")


def validate_against_preflight(manifest: dict[str, Any], preflight: dict[str, Any]) -> None:
    require(preflight.get("status") == "ready" and preflight.get("should_build") is True, "Expected preflight is not ready")
    require(manifest.get("release_name") == preflight.get("release_name"), "Manifest release differs from expected preflight")
    require(manifest.get("armbian") == preflight.get("armbian"), "Manifest Armbian provenance differs from preflight")
    require(manifest.get("bsp") == preflight.get("bsp"), "Manifest BSP provenance differs from preflight")
    for component in ("kernel", "uboot"):
        expected = object_value(preflight.get(component), f"preflight {component}")
        actual = object_value(manifest.get(component), f"manifest {component}")
        for key, value in expected.items():
            if key != "source_directory":
                require(actual.get(key) == value, f"Manifest {component}.{key} differs from preflight")
    expected_rkbin = copy.deepcopy(object_value(preflight.get("rkbin"), "preflight rkbin"))
    expected_rkbin.pop("source_directory", None)
    require(manifest.get("rkbin") == expected_rkbin, "Manifest rkbin provenance differs from preflight")
    require(manifest.get("maintainer") == preflight.get("maintainer"), "Manifest maintainer differs from preflight")
    actual_build = copy.deepcopy(object_value(manifest.get("build"), "manifest build"))
    actual_build.pop("workflow", None)
    require(actual_build == preflight.get("build"), "Manifest build settings differ from preflight")


def validate_stage(stage_dir: Path, module: dict[str, str], preflight: dict[str, Any] | None) -> dict[str, Any]:
    image, checksum_file, metadata_file, manifest_file = exact_stage_entries(stage_dir)
    raw_manifest = load_json(manifest_file)
    require(isinstance(raw_manifest, dict), "Build manifest must be a JSON object")
    manifest: dict[str, Any] = raw_manifest
    validate_manifest_policy(manifest, module)
    if preflight is not None:
        validate_against_preflight(manifest, preflight)

    declared_image = object_value(manifest["image"], "manifest image")
    require(declared_image.get("filename") == image.name, "Manifest image filename differs from staged image")
    require(declared_image.get("checksum_filename") == checksum_file.name, "Manifest checksum filename differs from staged checksum")
    require(declared_image.get("metadata_filename") == metadata_file.name, "Manifest metadata filename differs from staged metadata")
    actual_image_sha = sha256_file(image)
    require(actual_image_sha == parse_checksum(checksum_file, image.name), "Staged image checksum file does not match")
    require(actual_image_sha == declared_image["sha256"], "Staged image checksum differs from manifest")
    require(image.stat().st_size == declared_image["size_bytes"], "Staged image size differs from manifest")
    run(["xz", "-t", str(image)], capture=True)

    metadata = parse_image_metadata(metadata_file)
    armbian = manifest["armbian"]
    kernel = manifest["kernel"]
    maintainer = manifest["maintainer"]
    require(metadata["board"] == "Vontar-dq08", "Image metadata has the wrong board")
    require(metadata["revision"].startswith(armbian["version"]), "Image metadata revision differs from Armbian release")
    require(metadata["sources_rev"] == armbian["commit"][: len(metadata["sources_rev"])], "Image metadata Sources rev differs from Armbian commit")
    require(metadata["kernel"] == f'Linux {kernel["version"]} (current)', "Image metadata kernel differs from manifest")
    require(metadata["maintainer"] == f'{maintainer["name"]} <{maintainer["email"]}>', "Image metadata maintainer differs from manifest")
    reject_placeholder(metadata["maintainer"], "image metadata maintainer")
    filename_marker = f'_Vontar-dq08_bookworm_current_{kernel["version"]}_minimal.img.xz'
    require(image.name.endswith(filename_marker), "Image filename does not describe Bookworm/current/minimal")

    assets = manifest["assets"]
    for path in (image, checksum_file, metadata_file):
        record = object_value(assets.get(path.name), f"manifest asset {path.name}")
        require(record.get("size_bytes") == path.stat().st_size, f"Manifest size differs for {path.name}")
        require(record.get("sha256") == sha256_file(path), f"Manifest checksum differs for {path.name}")
    require(assets[image.name].get("role") == "image", "Image asset role is wrong")
    require(assets[checksum_file.name].get("role") == "checksum", "Checksum asset role is wrong")
    require(assets[metadata_file.name].get("role") == "metadata", "Metadata asset role is wrong")
    return manifest


def immutable_projection(manifest: dict[str, Any]) -> dict[str, Any]:
    projected = copy.deepcopy(manifest)
    build = object_value(projected.get("build"), "manifest build")
    build.pop("workflow", None)
    return projected


def validate_existing_draft(
    draft_dir: Path,
    stage_dir: Path,
    manifest: dict[str, Any],
    module: dict[str, str],
    preflight: dict[str, Any] | None,
) -> None:
    require(
        draft_dir.is_dir() and not draft_dir.is_symlink(),
        f"Invalid existing draft directory: {draft_dir}",
    )
    entries = list(draft_dir.iterdir())
    require(len(entries) <= 4, "Existing draft has more than four assets")
    require(
        all(path.is_file() and not path.is_symlink() for path in entries),
        "Existing draft assets must be regular, non-symlink files",
    )
    expected_names = {path.name for path in stage_dir.iterdir()}
    actual_names = {path.name for path in entries}
    if not actual_names <= expected_names:
        unexpected = ", ".join(sorted(actual_names - expected_names))
        raise ConflictError(f"Existing draft has unexpected assets: {unexpected}")

    for existing in entries:
        if existing.name == MANIFEST_NAME:
            loaded = load_json(existing)
            require(isinstance(loaded, dict), "Existing draft manifest must be a JSON object")
            draft_manifest: dict[str, Any] = loaded
            validate_manifest_policy(draft_manifest, module)
            if preflight is not None:
                validate_against_preflight(draft_manifest, preflight)
            if immutable_projection(draft_manifest) != immutable_projection(manifest):
                raise ConflictError(
                    f"Existing draft {manifest['release_name']} has different immutable provenance"
                )
        elif sha256_file(existing) != sha256_file(stage_dir / existing.name):
            raise ConflictError(
                f"Existing draft asset differs from the validated build: {existing.name}"
            )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--stage-dir", type=Path, required=True)
    result.add_argument("--module-conf", type=Path, default=Path("module.conf"))
    result.add_argument("--expected-preflight", type=Path)
    existing = result.add_mutually_exclusive_group()
    existing.add_argument("--existing-release-dir", type=Path, help="downloaded final assets for immutable rerun comparison")
    existing.add_argument("--existing-draft-dir", type=Path, help="downloaded partial draft assets for resumable publication")
    result.add_argument("--output", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        module = parse_module_conf(args.module_conf.resolve())
        expected: dict[str, Any] | None = None
        if args.expected_preflight is not None:
            loaded = load_json(args.expected_preflight.resolve())
            require(isinstance(loaded, dict), "Expected preflight JSON must be an object")
            expected = loaded
        manifest = validate_stage(args.stage_dir.resolve(), module, expected)
        status = "validated"
        should_publish = True
        if args.existing_release_dir is not None:
            existing = validate_stage(args.existing_release_dir.resolve(), module, None)
            if immutable_projection(existing) != immutable_projection(manifest):
                raise ConflictError(
                    f"Immutable release {manifest['release_name']} already exists with different provenance or assets"
                )
            status = "already_published"
            should_publish = False
        elif args.existing_draft_dir is not None:
            validate_existing_draft(
                args.existing_draft_dir.resolve(),
                args.stage_dir.resolve(),
                manifest,
                module,
                expected,
            )
            status = "validated_draft"
        result = {
            "schema_version": 1,
            "status": status,
            "should_publish": should_publish,
            "release_name": manifest["release_name"],
            "image_sha256": manifest["image"]["sha256"],
            "assets": sorted([*manifest["assets"], MANIFEST_NAME]),
        }
        rendered = dump_json(result, args.output)
        sys.stdout.write(rendered)
        return 0
    except ConflictError as exc:
        print(f"validate_release: {exc}", file=sys.stderr)
        return 4
    except (OSError, ReleaseError) as exc:
        print(f"validate_release: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
