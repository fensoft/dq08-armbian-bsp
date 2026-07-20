#!/usr/bin/env python3
"""Shared, dependency-free helpers for the DQ08 release pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
STABLE_ARMBIAN_TAG_RE = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")

REQUIRED_MODULE_KEYS = (
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

PLACEHOLDER_MARKERS = (
    "john doe",
    "jane doe",
    "somewhere.on.planet",
    "example.com",
    "example.org",
    "your name",
    "changeme",
    "todo",
    "unknown",
)


class ReleaseError(RuntimeError):
    """A deterministic release-policy violation."""


def fail(message: str) -> "NoReturn":  # type: ignore[name-defined]
    raise ReleaseError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ReleaseError(f"JSON input does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReleaseError(f"Invalid JSON in {path}: {exc}") from exc


def dump_json(data: Any, path: Path | None = None) -> str:
    rendered = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if path is not None:
        path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    return rendered


def parse_module_conf(path: Path) -> dict[str, str]:
    """Parse the deliberately simple KEY="value" metadata file without sourcing it."""
    values: dict[str, str] = {}
    assignment = re.compile(r'^([A-Z][A-Z0-9_]*)="([^"\\]*)"$')
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ReleaseError(f"module.conf does not exist: {path}") from exc
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = assignment.fullmatch(line)
        if not match:
            raise ReleaseError(
                f"Unsafe or unsupported module.conf syntax at {path}:{number}: {raw!r}"
            )
        key, value = match.groups()
        if key in values:
            raise ReleaseError(f"Duplicate module.conf key: {key}")
        values[key] = value
    missing = [key for key in REQUIRED_MODULE_KEYS if not values.get(key)]
    require(not missing, f"module.conf is missing required values: {', '.join(missing)}")
    validate_module_metadata(values)
    return values


def validate_module_metadata(values: Mapping[str, str]) -> None:
    version_tuple(values["DQ08_MODULE_VERSION"], "DQ08_MODULE_VERSION")
    require(values["DQ08_BOARD"] == "vontar-dq08", "DQ08_BOARD must be vontar-dq08")
    require(
        re.fullmatch(r"[1-9][0-9]*\.[0-9]+", values["DQ08_KERNEL_SERIES"]) is not None,
        "DQ08_KERNEL_SERIES must be a major.minor series",
    )
    require(
        values["DQ08_TESTED_KERNEL"].startswith(values["DQ08_KERNEL_SERIES"] + "."),
        "DQ08_TESTED_KERNEL is outside DQ08_KERNEL_SERIES",
    )
    for key in (
        "DQ08_TESTED_KERNEL_COMMIT",
        "DQ08_UBOOT_COMMIT",
        "DQ08_TESTED_ARMBIAN_COMMIT",
        "DQ08_SOURCE_BSP_COMMIT",
        "DQ08_RKBIN_COMMIT",
    ):
        require_sha1(values[key], key)
    for key in ("DQ08_RKBIN_DDR_SHA256", "DQ08_RKBIN_BL31_SHA256"):
        require_sha256(values[key], key)
    require(
        re.fullmatch(r"[0-9]{4}\.[0-9]{2}", values["DQ08_UBOOT_VERSION"]) is not None,
        "DQ08_UBOOT_VERSION must use YYYY.MM",
    )
    maintainer = f'{values["DQ08_MAINTAINER"]} <{values["DQ08_MAINTAINER_EMAIL"]}>'
    reject_placeholder(maintainer, "DQ08 maintainer")
    require(
        re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", values["DQ08_MAINTAINER_EMAIL"])
        is not None,
        "DQ08_MAINTAINER_EMAIL is not a valid email-shaped value",
    )


def version_tuple(value: str, label: str = "version") -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(value)
    require(match is not None, f"{label} must be an exact vMAJOR.MINOR.PATCH version: {value!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[union-attr,return-value]


def version_without_v(value: str) -> str:
    version_tuple(value)
    return value.removeprefix("v")


def require_sha1(value: str, label: str) -> str:
    require(SHA1_RE.fullmatch(value) is not None, f"{label} must be an exact 40-character lowercase commit SHA")
    return value


def require_sha256(value: str, label: str) -> str:
    require(SHA256_RE.fullmatch(value) is not None, f"{label} must be an exact lowercase SHA-256")
    return value


def reject_placeholder(value: str, label: str) -> None:
    lowered = value.casefold()
    marker = next((item for item in PLACEHOLDER_MARKERS if item in lowered), None)
    require(marker is None, f"{label} contains placeholder marker {marker!r}")


def release_name(armbian_tag: str, bsp_version: str) -> str:
    require(STABLE_ARMBIAN_TAG_RE.fullmatch(armbian_tag) is not None, f"Not a stable Armbian tag: {armbian_tag}")
    version_tuple(bsp_version, "BSP version")
    return f"dq08-armbian-{armbian_tag}-bsp-v{version_without_v(bsp_version)}"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(directory: Path) -> str:
    directory = directory.resolve()
    require(directory.is_dir(), f"Git directory does not exist: {directory}")
    result = run(
        [
            "git",
            "-c",
            f"safe.directory={directory}",
            "-C",
            str(directory),
            "rev-parse",
            "--verify",
            "HEAD^{commit}",
        ],
        capture=True,
    )
    return require_sha1(result.stdout.strip(), f"Git HEAD for {directory}")


def run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    capture: bool = False,
    attempts: int = 1,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    require(bool(command), "Refusing to run an empty command")
    require(attempts >= 1, "attempts must be at least one")
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    last: subprocess.CalledProcessError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return subprocess.run(
                list(command),
                cwd=cwd,
                env=full_env,
                check=True,
                text=True,
                stdout=subprocess.PIPE if capture else None,
                stderr=subprocess.PIPE if capture else None,
            )
        except subprocess.CalledProcessError as exc:
            last = exc
            if attempt < attempts:
                print(
                    f"command failed (attempt {attempt}/{attempts}); retrying: {command[0]}",
                    file=os.sys.stderr,
                    flush=True,
                )
    assert last is not None
    detail = ""
    if capture:
        detail = f"\nstdout:\n{last.stdout or ''}\nstderr:\n{last.stderr or ''}"
    raise ReleaseError(
        f"Command failed after {attempts} attempt(s) with exit {last.returncode}: "
        + " ".join(command)
        + detail
    ) from last


def extract_last_json_object(text: str, label: str) -> dict[str, Any]:
    for line in reversed(text.splitlines()):
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        require(isinstance(parsed, dict), f"{label} JSON must be an object")
        return parsed
    fail(f"Could not find a JSON object in {label} output")


def strings_in(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for nested in value.values():
            yield from strings_in(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from strings_in(nested)


def has_nested_string(value: Any, expected: str) -> bool:
    return any(item == expected or expected in item for item in strings_in(value))
