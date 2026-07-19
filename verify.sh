#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

module_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=module.conf
source "${module_root}/module.conf"
manifest="${module_root}/manifest.txt"
errors=0
file_count=0

while read -r mode relative_path; do
	[[ -n "${mode}" && "${mode}" != \#* ]] || continue
	file="${module_root}/${relative_path}"
	if [[ ! -f "${file}" ]]; then
		printf 'Missing: %s\n' "${file}" >&2
		errors=$((errors + 1))
	else
		actual_mode="$(stat -c '%a' "${file}")"
		if [[ "${actual_mode}" != "${mode#0}" ]]; then
			printf 'Mode mismatch: %s is %s, expected %s\n' "${file}" "${actual_mode}" "${mode#0}" >&2
			errors=$((errors + 1))
		fi
	fi
	file_count=$((file_count + 1))
done < "${manifest}"

bash -n "${module_root}/config/boards/vontar-dq08.csc"
bash -n "${module_root}/extensions/dq08-bsp/dq08-bsp.sh"
bash -n "${module_root}/install.sh" "${module_root}/uninstall.sh" "${module_root}/build.sh" "${module_root}/verify.sh"
python3 - "${module_root}/extensions/dq08-bsp/files/usr/libexec/dq08-front-panel" <<'PYTHON'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
compile(path.read_text(encoding="utf-8"), str(path), "exec")
PYTHON

if (($#)); then
	armbian_build="$1"
	[[ -d "${armbian_build}" ]] || { printf 'Not a directory: %s\n' "${armbian_build}" >&2; exit 2; }
	armbian_build="$(cd "${armbian_build}" && pwd -P)"
	while read -r mode relative_path; do
		[[ -n "${mode}" && "${mode}" != \#* ]] || continue
		if ! cmp -s "${module_root}/${relative_path}" "${armbian_build}/userpatches/${relative_path}"; then
			printf 'Not installed or different: %s\n' "${armbian_build}/userpatches/${relative_path}" >&2
			errors=$((errors + 1))
		fi
	done < "${manifest}"
fi

if ((errors)); then
	printf 'Verification failed with %d error(s).\n' "${errors}" >&2
	exit 1
fi
printf '%s %s verified: %d managed files, kernel series %s.\n' "${DQ08_MODULE_NAME}" "${DQ08_MODULE_VERSION}" "${file_count}" "${DQ08_KERNEL_SERIES}"
