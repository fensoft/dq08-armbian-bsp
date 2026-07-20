#!/usr/bin/env python3
"""Select the oldest unpublished stable Armbian tag for a DQ08 release."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from _lib import (
    ReleaseError,
    STABLE_ARMBIAN_TAG_RE,
    dump_json,
    git_commit,
    load_json,
    parse_module_conf,
    release_name,
    require,
    require_sha1,
    run,
    version_tuple,
)


BASELINE = "v26.5.1"


def tags_from_repository(repository: Path) -> dict[str, str]:
    repository = repository.resolve()
    git_commit(repository)
    result = run(
        ["git", "-C", str(repository), "tag", "--list", "v*"], capture=True
    )
    tags: dict[str, str] = {}
    for name in result.stdout.splitlines():
        if STABLE_ARMBIAN_TAG_RE.fullmatch(name) is None:
            continue
        resolved = run(
            ["git", "-C", str(repository), "rev-parse", "--verify", f"{name}^{{commit}}"],
            capture=True,
        ).stdout.strip()
        tags[name] = require_sha1(resolved, f"commit for {name}")
    return tags


def tags_from_json(path: Path) -> dict[str, str]:
    raw = load_json(path)
    if isinstance(raw, dict) and "tags" in raw:
        raw = raw["tags"]
    if isinstance(raw, dict):
        raw = [{"name": key, "commit": value} for key, value in raw.items()]
    require(isinstance(raw, list), "tags JSON must be a list, a tag-to-commit object, or {tags: [...]}")
    tags: dict[str, str] = {}
    for index, item in enumerate(raw):
        require(isinstance(item, dict), f"tags[{index}] must be an object")
        name = item.get("name") or item.get("tag")
        commit = item.get("commit") or item.get("sha")
        if name is None and isinstance(item.get("ref"), str):
            name = item["ref"].removeprefix("refs/tags/")
        if commit is None and isinstance(item.get("object"), dict):
            commit = item["object"].get("sha")
        require(isinstance(name, str) and name, f"tags[{index}] has no tag name")
        require(isinstance(commit, str), f"tags[{index}] has no resolved commit")
        commit = require_sha1(commit, f"commit for {name}")
        previous = tags.get(name)
        require(previous in (None, commit), f"Tag {name} appears with multiple commits")
        tags[name] = commit
    return tags


def complete_release_asset_names(value: Any) -> set[str] | None:
    if not isinstance(value, list):
        return None
    names: list[str] = []
    for asset in value:
        if isinstance(asset, str):
            name = asset
        elif isinstance(asset, dict) and isinstance(asset.get("name"), str):
            name = asset["name"]
        else:
            return None
        if not name or Path(name).name != name:
            return None
        names.append(name)
    if len(names) != 4 or len(set(names)) != 4:
        return None
    images = [name for name in names if name.endswith(".img.xz")]
    if len(images) != 1:
        return None
    image = images[0]
    expected = {
        image,
        f"{image}.sha",
        f"{image.removesuffix('.xz')}.txt",
        "build-manifest.json",
    }
    return expected if set(names) == expected else None


def release_names(path: Path) -> set[str]:
    raw = load_json(path)
    if isinstance(raw, dict) and "releases" in raw:
        raw = raw["releases"]
    require(isinstance(raw, list), "releases JSON must be a list or {releases: [...]}")
    names: set[str] = set()
    for index, item in enumerate(raw):
        require(isinstance(item, (str, dict)), f"releases[{index}] must be a string or object")
        # A bare name or incomplete API projection cannot prove that publication
        # finished. Ignore it so discovery selects the tag and hosted publication
        # can validate or report the malformed existing release.
        if not isinstance(item, dict):
            continue
        if item.get("draft") is not False or item.get("prerelease") is not False:
            continue
        if complete_release_asset_names(item.get("assets")) is None:
            continue
        tag_name = item.get("tag_name")
        if isinstance(tag_name, str) and tag_name:
            names.add(tag_name)
    return names


def load_state(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"schema_version": 1, "armbian_tags": {}}
    raw = load_json(path)
    require(isinstance(raw, dict), "state JSON must be an object")
    require(raw.get("schema_version", 1) == 1, "Unsupported state schema_version")
    mappings = raw.get("armbian_tags", {})
    require(isinstance(mappings, dict), "state armbian_tags must be an object")
    normalized: dict[str, str] = {}
    for tag, commit in mappings.items():
        require(isinstance(tag, str), "state tag names must be strings")
        require(isinstance(commit, str), f"state commit for {tag} must be a string")
        normalized[tag] = require_sha1(commit, f"state commit for {tag}")
    return {"schema_version": 1, "armbian_tags": normalized}


def discover(
    tags: dict[str, str],
    published: set[str],
    state: dict[str, Any],
    bsp_version: str,
    baseline: str = BASELINE,
    requested_tag: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    baseline_key = version_tuple(baseline, "baseline")
    stable = {
        tag: commit
        for tag, commit in tags.items()
        if STABLE_ARMBIAN_TAG_RE.fullmatch(tag) is not None
        and version_tuple(tag, f"Armbian tag {tag}") >= baseline_key
    }
    require(stable, f"No stable Armbian tags found at or after {baseline}")

    recorded: dict[str, str] = state["armbian_tags"]
    for tag, old_commit in recorded.items():
        if STABLE_ARMBIAN_TAG_RE.fullmatch(tag) is None or version_tuple(tag) < baseline_key:
            continue
        require(tag in stable, f"Previously recorded Armbian tag disappeared: {tag}")
        require(
            stable[tag] == old_commit,
            f"Armbian tag moved: {tag} was {old_commit}, now {stable[tag]}",
        )

    next_tags = dict(recorded)
    next_tags.update(stable)
    next_state = {
        "schema_version": 1,
        "armbian_tags": dict(sorted(next_tags.items(), key=lambda pair: version_tuple(pair[0]))),
    }

    selected: tuple[str, str, str] | None = None
    if requested_tag is not None:
        require(
            STABLE_ARMBIAN_TAG_RE.fullmatch(requested_tag) is not None,
            f"Requested tag is not a stable point release: {requested_tag}",
        )
        require(
            version_tuple(requested_tag, "requested tag") >= baseline_key,
            f"Requested tag {requested_tag} is older than baseline {baseline}",
        )
        require(requested_tag in stable, f"Requested tag was not found: {requested_tag}")
        selected = (
            requested_tag,
            stable[requested_tag],
            release_name(requested_tag, bsp_version),
        )
    else:
        for tag in sorted(stable, key=version_tuple):
            expected_name = release_name(tag, bsp_version)
            if expected_name not in published:
                selected = (tag, stable[tag], expected_name)
                break

    if selected is None:
        result: dict[str, Any] = {
            "schema_version": 1,
            "status": "up_to_date",
            "should_build": False,
            "baseline": baseline,
            "bsp_version": f"v{bsp_version.removeprefix('v')}",
            "armbian_tag": None,
            "armbian_version": None,
            "armbian_commit": None,
            "release_name": None,
            "already_published": False,
        }
    else:
        tag, commit, expected_name = selected
        result = {
            "schema_version": 1,
            "status": "selected",
            "should_build": True,
            "baseline": baseline,
            "bsp_version": f"v{bsp_version.removeprefix('v')}",
            "armbian_tag": tag,
            "armbian_version": tag.removeprefix("v"),
            "armbian_commit": commit,
            "release_name": expected_name,
            "already_published": expected_name in published,
        }
    result["state_changed"] = next_state != state
    return result, next_state


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    source = result.add_mutually_exclusive_group(required=True)
    source.add_argument("--armbian-repo", type=Path, help="local Armbian clone with fetched tags")
    source.add_argument("--tags-json", type=Path, help="resolved tag/commit fixture JSON")
    result.add_argument("--releases-json", required=True, type=Path, help="GitHub release-list JSON")
    result.add_argument("--state-json", type=Path, help="previous automation state JSON; missing means empty")
    result.add_argument("--module-conf", type=Path, default=Path("module.conf"))
    result.add_argument("--baseline", default=BASELINE)
    result.add_argument("--requested-tag", help="manually select this exact stable tag")
    result.add_argument("--output", type=Path, help="also atomically write selection JSON here")
    result.add_argument("--next-state", type=Path, help="atomically write updated tag state here")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        module = parse_module_conf(args.module_conf.resolve())
        tags = (
            tags_from_repository(args.armbian_repo)
            if args.armbian_repo is not None
            else tags_from_json(args.tags_json)
        )
        result, next_state = discover(
            tags,
            release_names(args.releases_json),
            load_state(args.state_json),
            module["DQ08_MODULE_VERSION"],
            args.baseline,
            args.requested_tag,
        )
        if args.next_state is not None:
            dump_json(next_state, args.next_state)
        rendered = dump_json(result, args.output)
        sys.stdout.write(rendered)
        return 0
    except ReleaseError as exc:
        print(f"discover_release: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
