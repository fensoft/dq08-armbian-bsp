#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

usage() {
	printf 'Usage: ./uninstall.sh [--force] [--dry-run] ARMBIAN_BUILD\n'
}

module_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
manifest="${module_root}/manifest.txt"
force="no"
dry_run="no"
armbian_build=""

while (($#)); do
	case "$1" in
		--force) force="yes" ;;
		--dry-run) dry_run="yes" ;;
		-h | --help) usage; exit 0 ;;
		--*) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
		*) [[ -z "${armbian_build}" ]] || { usage >&2; exit 2; }; armbian_build="$1" ;;
	esac
	shift
done

[[ -n "${armbian_build}" && -d "${armbian_build}" ]] || { usage >&2; exit 2; }
armbian_build="$(cd "${armbian_build}" && pwd -P)"
[[ "${armbian_build}" != "/" && -f "${armbian_build}/compile.sh" ]] || {
	printf 'Unsafe or invalid Armbian target: %s\n' "${armbian_build}" >&2
	exit 2
}
userpatches_root="${armbian_build}/userpatches"
declare -a conflicts=()

while read -r mode relative_path; do
	[[ -n "${mode}" && "${mode}" != \#* ]] || continue
	case "${relative_path}" in "" | /* | *../* | ../*) printf 'Unsafe manifest path: %s\n' "${relative_path}" >&2; exit 2 ;; esac
	source_file="${module_root}/${relative_path}"
	destination_file="${userpatches_root}/${relative_path}"
	if [[ -e "${destination_file}" || -L "${destination_file}" ]]; then
		if ! cmp -s "${source_file}" "${destination_file}" && [[ "${force}" != "yes" ]]; then
			conflicts+=("${destination_file}")
		fi
	fi
done < "${manifest}"

if ((${#conflicts[@]})); then
	printf 'Refusing to remove locally modified files:\n' >&2
	printf '  %s\n' "${conflicts[@]}" >&2
	printf 'Use --force only if deleting those changes is intended.\n' >&2
	exit 3
fi

while read -r mode relative_path; do
	[[ -n "${mode}" && "${mode}" != \#* ]] || continue
	destination_file="${userpatches_root}/${relative_path}"
	[[ -e "${destination_file}" || -L "${destination_file}" ]] || continue
	if [[ "${dry_run}" == "yes" ]]; then
		printf 'Would remove %s\n' "${destination_file}"
	else
		rm -- "${destination_file}"
		printf 'Removed %s\n' "${destination_file}"
		directory="$(dirname "${destination_file}")"
		while [[ "${directory}" != "${userpatches_root}" ]]; do
			rmdir "${directory}" 2>/dev/null || break
			directory="$(dirname "${directory}")"
		done
	fi
done < "${manifest}"

printf 'DQ08 BSP module %s. Unrelated userpatches were preserved.\n' "$([[ "${dry_run}" == "yes" ]] && printf 'checked for removal' || printf 'removed')"
