#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

export LC_ALL=C

die() {
	printf 'ERROR: %s\n' "$*" >&2
	exit 1
}

usage() {
	printf 'Usage: sudo %s IMAGE.img.xz /dev/disk/by-id/LEXAR_WHOLE_DISK\n' \
		"${0##*/}" >&2
}

if (($# != 2)); then
	usage
	exit 2
fi

((EUID == 0)) || die "run this command through sudo"
[[ -t 0 ]] || die "interactive confirmation requires a terminal"

for required_command in \
	awk blockdev dd find findmnt head lsblk readlink sed sha256sum \
	swapon xz; do
	command -v "${required_command}" >/dev/null 2>&1 ||
		die "${required_command} is required"
done

image_argument="$1"
device_link="$2"

[[ -f "${image_argument}" ]] || die "image not found: ${image_argument}"
image="$(readlink -f -- "${image_argument}")"
[[ "${image}" == *.img.xz ]] ||
	die "IMAGE must resolve to an Armbian .img.xz file"

[[ "${device_link}" == /dev/disk/by-id/* ]] ||
	die "DEVICE must be a stable /dev/disk/by-id/ path"
[[ "${device_link}" == "/dev/disk/by-id/${device_link##*/}" ]] ||
	die "DEVICE must be a direct link inside /dev/disk/by-id"
[[ "${device_link##*/}" != *-part* ]] ||
	die "DEVICE must be the whole-disk by-id link, not a partition link"
[[ -L "${device_link}" ]] ||
	die "DEVICE is not a /dev/disk/by-id symlink: ${device_link}"

device="$(readlink -f -- "${device_link}")"
[[ -b "${device}" ]] || die "DEVICE does not resolve to a block device"

lsblk_value() {
	local column="$1"
	local node="$2"
	local value

	if [[ "${column}" == "SIZE" ]]; then
		value="$(lsblk -bdnro "${column}" -- "${node}")" ||
			die "could not read ${column} for ${node}"
	else
		value="$(lsblk -dnro "${column}" -- "${node}")" ||
			die "could not read ${column} for ${node}"
	fi
	[[ "${value}" != *$'\n'* ]] ||
		die "ambiguous ${column} result for ${node}"
	printf '%s' "${value}"
}

trim_trailing_space() {
	sed 's/[[:space:]]*$//'
}

device_type="$(lsblk_value TYPE "${device}")"
read_only="$(lsblk_value RO "${device}")"
removable="$(lsblk_value RM "${device}")"
device_size="$(lsblk_value SIZE "${device}")"
device_majmin="$(lsblk_value MAJ:MIN "${device}")"
transport="$(lsblk_value TRAN "${device}" | trim_trailing_space)"
vendor="$(lsblk_value VENDOR "${device}" | trim_trailing_space)"
model="$(lsblk_value MODEL "${device}" | trim_trailing_space)"
serial="$(lsblk_value SERIAL "${device}" | trim_trailing_space)"
identity="${vendor} ${model} ${serial}"

[[ "${device_type}" == "disk" ]] ||
	die "DEVICE must resolve to a whole disk, not ${device_type:-an unknown type}"
[[ "${read_only}" == "0" ]] || die "target is read-only"
[[ "${removable}" == "1" ]] ||
	die "target is not marked removable by the kernel"
[[ "${device_size}" =~ ^[0-9]+$ ]] ||
	die "could not determine target size"
((device_size >= 55000000000 && device_size <= 70000000000)) ||
	die "target is not a nominal 64 GB device (${device_size} bytes)"
[[ "${identity,,}" == *lexar* ]] ||
	die "target identity does not contain 'Lexar': ${identity:-unknown}"

device_node_output="$(lsblk -nrpo NAME -- "${device}")" ||
	die "could not enumerate the target disk and its children"
[[ -n "${device_node_output}" ]] ||
	die "target disk enumeration returned no devices"
mapfile -t device_nodes <<< "${device_node_output}"
((${#device_nodes[@]} > 0)) ||
	die "could not enumerate the target disk and its children"
[[ "${device_nodes[0]}" == "${device}" ]] ||
	die "unexpected target enumeration for ${device}"

root_majmin="$(findmnt -rn -o MAJ:MIN --target /)" ||
	die "could not identify the root filesystem"
[[ "${root_majmin}" =~ ^[0-9]+:[0-9]+$ ]] ||
	die "invalid root-filesystem device identity: ${root_majmin:-unknown}"
root_sysfs="/sys/dev/block/${root_majmin}"
[[ -e "${root_sysfs}" ]] ||
	die "root filesystem is not backed by an identifiable block device"
root_block_name="$(readlink -f -- "${root_sysfs}")" ||
	die "could not resolve the root block device"
root_block_name="${root_block_name##*/}"
root_device="/dev/${root_block_name}"
[[ -b "${root_device}" ]] ||
	die "root filesystem block device is unavailable: ${root_device}"

root_ancestry_output="$(lsblk -srnpo NAME -- "${root_device}")" ||
	die "could not enumerate root-device ancestry"
[[ -n "${root_ancestry_output}" ]] ||
	die "root-device ancestry enumeration returned no devices"
mapfile -t root_ancestry <<< "${root_ancestry_output}"
((${#root_ancestry[@]} > 0)) ||
	die "could not enumerate root-device ancestry"
for root_node in "${root_ancestry[@]}"; do
	root_node="$(readlink -f -- "${root_node}")" ||
		die "could not resolve root-device ancestor"
	[[ "${root_node}" != "${device}" ]] ||
		die "target is an ancestor of the running system root: ${device}"
done

assert_target_idle() {
	local node holders_dir holder_entry mount_targets mount_status
	local current_node_output swap_name swap_real swap_output

	[[ "$(readlink -f -- "${device_link}")" == "${device}" ]] ||
		die "DEVICE symlink changed after validation"
	[[ "$(lsblk_value MAJ:MIN "${device}")" == "${device_majmin}" ]] ||
		die "target device changed after validation"
	[[ "$(lsblk_value SIZE "${device}")" == "${device_size}" ]] ||
		die "target size changed after validation"
	[[ "$(lsblk_value MODEL "${device}" | trim_trailing_space)" == "${model}" ]] ||
		die "target model changed after validation"
	[[ "$(lsblk_value SERIAL "${device}" | trim_trailing_space)" == "${serial}" ]] ||
		die "target serial changed after validation"
	current_node_output="$(lsblk -nrpo NAME -- "${device}")" ||
		die "could not re-enumerate target nodes"
	[[ "${current_node_output}" == "${device_node_output}" ]] ||
		die "target partition topology changed after validation"

	for node in "${device_nodes[@]}"; do
		[[ -b "${node}" ]] ||
			die "target node disappeared after validation: ${node}"

		mount_targets=""
		if mount_targets="$(findmnt -rn -S "${node}" -o TARGET)"; then
			mount_targets="${mount_targets//$'\n'/, }"
			die "${node} is mounted at ${mount_targets}; unmount it manually"
		else
			mount_status=$?
			((mount_status == 1)) ||
				die "could not determine mount state for ${node}"
		fi

		holders_dir="/sys/class/block/${node##*/}/holders"
		[[ -d "${holders_dir}" ]] ||
			die "could not inspect holders for ${node}"
		holder_entry="$(
			find "${holders_dir}" -mindepth 1 -maxdepth 1 -print -quit
		)" || die "could not inspect holders for ${node}"
		if [[ -n "${holder_entry}" ]]; then
			die "${node} has active holders; deactivate them manually"
		fi
	done

	swap_output="$(swapon --noheadings --raw --show=NAME)" ||
		die "could not determine active swap devices"
	while IFS= read -r swap_name; do
		[[ -n "${swap_name}" ]] || continue
		if [[ -b "${swap_name}" ]]; then
			swap_real="$(readlink -f -- "${swap_name}")"
			for node in "${device_nodes[@]}"; do
				[[ "$(readlink -f -- "${node}")" != "${swap_real}" ]] ||
					die "${node} is active swap"
			done
		fi
	done <<< "${swap_output}"
}

assert_target_idle

sidecar="${image}.sha"
[[ -f "${sidecar}" ]] ||
	die "required Armbian checksum sidecar is missing: ${sidecar}"
image_dir="${image%/*}"
[[ -n "${image_dir}" ]] || image_dir="/"
image_basename="${image##*/}"
sidecar_basename="${sidecar##*/}"
if ! awk -v expected="${image_basename}" '
	NF {
		count++
		name = $0
		sub(/^[^[:space:]]+[[:space:]]+[*]?/, "", name)
		if (name == expected)
			match_count++
	}
	END {
		exit !(count == 1 && match_count == 1)
	}
' "${sidecar}"; then
	die "checksum sidecar must contain exactly one record for ${image_basename}"
fi

printf 'Validating compressed-image checksum...\n'
(
	cd "${image_dir}"
	sha256sum --check --strict -- "${sidecar_basename}"
) || die "compressed-image checksum validation failed"

printf 'Testing XZ stream...\n'
xz --test -- "${image}" || die "XZ integrity test failed"
raw_size="$(
	xz --robot --list -- "${image}" |
		awk -F '\t' '
			$1 == "totals" {
				count++
				size = $5
			}
			END {
				if (count != 1 || size !~ /^[1-9][0-9]*$/)
					exit 1
				print size
			}
	'
)" || die "could not determine uncompressed image size"
((raw_size <= device_size)) ||
	die "uncompressed image is larger than the target"

printf 'Computing decompressed source checksum...\n'
expected_hash="$(
	xz --decompress --stdout -- "${image}" |
		sha256sum |
		awk '{print $1}'
)" || die "could not checksum the decompressed image"
[[ "${expected_hash}" =~ ^[0-9a-f]{64}$ ]] ||
	die "invalid decompressed source checksum"

size_gib="$(awk -v bytes="${device_size}" 'BEGIN { printf "%.2f", bytes / 1073741824 }')"
printf '\n'
printf 'IMAGE       : %s\n' "${image}"
printf 'RAW BYTES   : %s\n' "${raw_size}"
printf 'TARGET LINK : %s\n' "${device_link}"
printf 'TARGET NODE : %s\n' "${device}"
printf 'VENDOR      : %s\n' "${vendor:-unknown}"
printf 'MODEL       : %s\n' "${model:-unknown}"
printf 'SERIAL      : %s\n' "${serial:-unknown}"
printf 'SIZE        : %s bytes (%s GiB)\n' "${device_size}" "${size_gib}"
printf 'TRANSPORT   : %s\n\n' "${transport:-unknown}"

confirmation="FLASH ${device_link} ${serial:-NO-SERIAL}"
printf 'This irreversibly overwrites the entire target disk.\n'
printf 'Type exactly: %s\n> ' "${confirmation}"
IFS= read -r answer
[[ "${answer}" == "${confirmation}" ]] ||
	die "confirmation did not match; nothing was written"

# The confirmation may take arbitrarily long. Fail if the link, identity, mount,
# swap, or holder state changed while waiting.
assert_target_idle

printf 'Writing %s bytes to %s...\n' "${raw_size}" "${device}"
xz --decompress --stdout -- "${image}" |
	dd of="${device}" bs=4M iflag=fullblock conv=fsync status=progress ||
	die "image write failed"
blockdev --flushbufs "${device}" ||
	die "could not flush and invalidate target buffers"

printf 'Reading back and hashing all %s written bytes...\n' "${raw_size}"
actual_hash="$(
	head -c "${raw_size}" -- "${device}" |
		sha256sum |
		awk '{print $1}'
)" || die "target read-back failed"
[[ "${actual_hash}" =~ ^[0-9a-f]{64}$ ]] ||
	die "invalid target read-back checksum"
[[ "${actual_hash}" == "${expected_hash}" ]] ||
	die "read-back checksum mismatch (expected ${expected_hash}, got ${actual_hash})"

printf 'Flash verified: %s\n' "${device_link}"
printf 'SHA256 (uncompressed): %s\n' "${actual_hash}"
printf 'Reinsert the Lexar media before booting it.\n'
