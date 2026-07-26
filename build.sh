#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

module_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=module.conf
source "${module_root}/module.conf"

if (($# < 1)); then
	printf 'Usage: ./build.sh ARMBIAN_BUILD [RELEASE] [KEY=value ...]\n' >&2
	exit 2
fi

armbian_build="$1"
shift
release="${1:-bookworm}"
if (($#)); then shift; fi

for argument in "$@"; do
	case "${argument}" in
	IMAGE_VERSION|IMAGE_VERSION=*)
		printf 'IMAGE_VERSION is managed by this BSP wrapper and cannot be overridden.\n' >&2
		exit 2
		;;
	esac
done

"${module_root}/install.sh" "${armbian_build}"
armbian_build="$(cd "${armbian_build}" && pwd -P)"

armbian_version_file="${armbian_build}/VERSION"
[[ -f "${armbian_version_file}" ]] || {
	printf 'Armbian VERSION file is missing: %s\n' "${armbian_version_file}" >&2
	exit 2
}
armbian_revision="$(< "${armbian_version_file}")"
if [[ ! "${armbian_revision}" =~ ^[0-9A-Za-z][0-9A-Za-z._+-]*$ ]]; then
	printf 'Unsafe Armbian VERSION value: %q\n' "${armbian_revision}" >&2
	exit 2
fi
image_version="${armbian_revision}-bsp-v${DQ08_MODULE_VERSION}"

exec "${armbian_build}/compile.sh" build \
	BOARD="${DQ08_BOARD}" \
	BRANCH=current \
	RELEASE="${release}" \
	BUILD_MINIMAL=yes \
	BUILD_DESKTOP=no \
	KERNEL_CONFIGURE=no \
	MAINTAINER="${DQ08_MAINTAINER}" \
	MAINTAINERMAIL="${DQ08_MAINTAINER_EMAIL}" \
	PREFER_DOCKER=yes \
	"$@" \
	IMAGE_VERSION="${image_version}"
