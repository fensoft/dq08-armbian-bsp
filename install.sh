#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

usage() {
	cat <<'EOF'
Usage: ./install.sh [--force] [--dry-run] [--allow-unsupported] ARMBIAN_BUILD

Install this module into ARMBIAN_BUILD/userpatches without touching Armbian's
tracked config/ or patch/ trees. Existing different files are refused unless
--force is supplied.
EOF
}

module_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=module.conf
source "${module_root}/module.conf"
manifest="${module_root}/manifest.txt"
force="no"
dry_run="no"
allow_unsupported="no"
armbian_build=""

while (($#)); do
	case "$1" in
		--force) force="yes" ;;
		--dry-run) dry_run="yes" ;;
		--allow-unsupported) allow_unsupported="yes" ;;
		-h | --help) usage; exit 0 ;;
		--*) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
		*)
			[[ -z "${armbian_build}" ]] || { printf 'Only one Armbian path is accepted.\n' >&2; exit 2; }
			armbian_build="$1"
			;;
	esac
	shift
done

[[ -n "${armbian_build}" ]] || { usage >&2; exit 2; }
[[ -d "${armbian_build}" ]] || { printf 'Not a directory: %s\n' "${armbian_build}" >&2; exit 2; }
armbian_build="$(cd "${armbian_build}" && pwd -P)"

[[ "${armbian_build}" != "/" && "${armbian_build}" != "${module_root}" ]] || {
	printf 'Unsafe Armbian target: %s\n' "${armbian_build}" >&2
	exit 2
}
[[ -f "${armbian_build}/compile.sh" && -d "${armbian_build}/config/boards" ]] || {
	printf 'Not an Armbian build checkout: %s\n' "${armbian_build}" >&2
	exit 2
}

kernel_common="${armbian_build}/config/sources/families/include/rockchip64_common.inc"
current_series=""
if [[ -f "${kernel_common}" ]]; then
	current_series="$(sed -n '/^[[:space:]]*current)/,/^[[:space:]]*;;/p' "${kernel_common}" | sed -n 's/.*KERNEL_MAJOR_MINOR="\([^"]*\)".*/\1/p' | head -n 1)"
fi
if [[ "${current_series}" != "${DQ08_KERNEL_SERIES}" ]]; then
	printf 'Armbian rockchip64 current is %s; this module targets %s.\n' "${current_series:-unknown}" "${DQ08_KERNEL_SERIES}" >&2
	if [[ "${allow_unsupported}" != "yes" ]]; then
		printf 'Use the tested Armbian commit or pass --allow-unsupported after reviewing the port.\n' >&2
		exit 2
	fi
fi

armbian_head="$(git -C "${armbian_build}" rev-parse HEAD 2>/dev/null || true)"
if [[ -n "${armbian_head}" && "${armbian_head}" != "${DQ08_TESTED_ARMBIAN_COMMIT}" ]]; then
	printf 'Warning: tested on Armbian %s; target is %s.\n' "${DQ08_TESTED_ARMBIAN_COMMIT}" "${armbian_head}" >&2
fi

declare -a conflicts=()
file_count=0
while read -r mode relative_path; do
	[[ -n "${mode}" && "${mode}" != \#* ]] || continue
	case "${relative_path}" in
		"" | /* | *../* | ../*) printf 'Unsafe manifest path: %s\n' "${relative_path}" >&2; exit 2 ;;
	esac
	source_file="${module_root}/${relative_path}"
	destination_file="${armbian_build}/userpatches/${relative_path}"
	[[ -f "${source_file}" ]] || { printf 'Missing module file: %s\n' "${source_file}" >&2; exit 2; }
	if [[ -e "${destination_file}" || -L "${destination_file}" ]]; then
		if ! cmp -s "${source_file}" "${destination_file}" && [[ "${force}" != "yes" ]]; then
			conflicts+=("${destination_file}")
		fi
	fi
	file_count=$((file_count + 1))
done < "${manifest}"

if ((${#conflicts[@]})); then
	printf 'Refusing to overwrite different files:\n' >&2
	printf '  %s\n' "${conflicts[@]}" >&2
	printf 'Review them, then rerun with --force if replacement is intended.\n' >&2
	exit 3
fi

while read -r mode relative_path; do
	[[ -n "${mode}" && "${mode}" != \#* ]] || continue
	source_file="${module_root}/${relative_path}"
	destination_file="${armbian_build}/userpatches/${relative_path}"
	if [[ "${dry_run}" == "yes" ]]; then
		printf 'Would install %s -> %s (mode %s)\n' "${relative_path}" "${destination_file}" "${mode}"
	else
		install -D -m "${mode}" "${source_file}" "${destination_file}"
		printf 'Installed %s\n' "${destination_file}"
	fi
done < "${manifest}"

printf '%s %s: %s %d files for BOARD=%s.\n' "${DQ08_MODULE_NAME}" "${DQ08_MODULE_VERSION}" "$([[ "${dry_run}" == "yes" ]] && printf 'checked' || printf 'installed')" "${file_count}" "${DQ08_BOARD}"
