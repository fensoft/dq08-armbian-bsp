#!/usr/bin/env python3
"""Extract the four flat release files without trusting tar paths or links."""

from __future__ import annotations

import argparse
import re
import shutil
import tarfile
from pathlib import Path


SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
GITHUB_ASSET_LIMIT = 2 * 1024 * 1024 * 1024
SMALL_ASSET_LIMIT = 16 * 1024 * 1024
BUNDLE_CONTENT_LIMIT = 2_200_000_000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()

    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise SystemExit(f"destination is not empty: {destination}")

    with tarfile.open(args.archive, mode="r:") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(members) != 4 or len(set(names)) != 4:
            raise SystemExit("release archive must contain exactly four unique members")
        for member in members:
            if not member.isfile():
                raise SystemExit(f"release archive member is not a regular file: {member.name}")
            if Path(member.name).name != member.name or not SAFE_NAME.fullmatch(member.name):
                raise SystemExit(f"unsafe release archive member name: {member.name!r}")
            limit = GITHUB_ASSET_LIMIT if member.name.endswith(".img.xz") else SMALL_ASSET_LIMIT
            if member.size < 1 or member.size >= limit:
                raise SystemExit(
                    f"release archive member has invalid size {member.size}: {member.name}"
                )
        if sum(member.size for member in members) > BUNDLE_CONTENT_LIMIT:
            raise SystemExit("release archive declares more than 2.2 GB of content")

        expected_counts = {
            "build-manifest.json": sum(name == "build-manifest.json" for name in names),
            "img.xz": sum(name.endswith(".img.xz") for name in names),
            "img.xz.sha": sum(name.endswith(".img.xz.sha") for name in names),
            "img.txt": sum(name.endswith(".img.txt") for name in names),
        }
        if any(count != 1 for count in expected_counts.values()):
            raise SystemExit(f"unexpected release archive layout: {expected_counts}")

        for member in members:
            source = archive.extractfile(member)
            if source is None:
                raise SystemExit(f"cannot read release archive member: {member.name}")
            with source, (destination / member.name).open("xb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)

    print(f"Safely extracted {len(members)} release files into {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
