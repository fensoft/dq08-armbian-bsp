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

"${module_root}/install.sh" "${armbian_build}"
armbian_build="$(cd "${armbian_build}" && pwd -P)"

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
	"$@"
