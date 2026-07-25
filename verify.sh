#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

module_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=module.conf
source "${module_root}/module.conf"
manifest="${module_root}/manifest.txt"
errors=0
file_count=0

for commit_var in \
	DQ08_TESTED_KERNEL_COMMIT \
	DQ08_UBOOT_COMMIT \
	DQ08_TESTED_ARMBIAN_COMMIT \
	DQ08_SOURCE_BSP_COMMIT \
	DQ08_RKBIN_COMMIT \
	DQ08_BCM4335_FIRMWARE_COMMIT; do
	commit_value="${!commit_var}"
	if [[ ! "${commit_value}" =~ ^[0-9a-f]{40}$ ]]; then
		printf 'Invalid %s: %s\n' "${commit_var}" "${commit_value}" >&2
		errors=$((errors + 1))
	fi
done

for checksum_var in \
	DQ08_RKBIN_DDR_SHA256 \
	DQ08_RKBIN_BL31_SHA256 \
	DQ08_BCM4335_WIFI_SHA256 \
	DQ08_BCM4335_NVRAM_SHA256 \
	DQ08_BCM4335_BT_A0_SHA256 \
	DQ08_BCM4335_BT_B0_SHA256 \
	DQ08_BCM4335_BT_C0_SHA256; do
	checksum_value="${!checksum_var}"
	if [[ ! "${checksum_value}" =~ ^[0-9a-f]{64}$ ]]; then
		printf 'Invalid %s: %s\n' "${checksum_var}" "${checksum_value}" >&2
		errors=$((errors + 1))
	fi
done

[[ -n "${DQ08_MAINTAINER}" && -n "${DQ08_MAINTAINER_EMAIL}" ]] || {
	printf 'Maintainer name and email must not be empty.\n' >&2
	errors=$((errors + 1))
}
if printf '%s\n%s\n' "${DQ08_MAINTAINER}" "${DQ08_MAINTAINER_EMAIL}" | grep -Eqi \
	'john[._ -]*doe|somewhere[.]on[.]planet|example[.](com|org|net)|(^|[^[:alnum:]])(todo|unknown)([^[:alnum:]]|$)'; then
	printf 'Maintainer metadata contains a placeholder.\n' >&2
	errors=$((errors + 1))
fi

if [[ ! "${DQ08_KERNEL_SERIES}" =~ ^[0-9]+[.][0-9]+$ || "${DQ08_TESTED_KERNEL}" != "${DQ08_KERNEL_SERIES}."* ]]; then
	printf 'Tested kernel %s does not match series %s.\n' "${DQ08_TESTED_KERNEL}" "${DQ08_KERNEL_SERIES}" >&2
	errors=$((errors + 1))
fi

extension_file="${module_root}/extensions/dq08-bsp/dq08-bsp.sh"
for expected_assignment in \
	"DQ08_RKBIN_COMMIT=\"${DQ08_RKBIN_COMMIT}\"" \
	"DQ08_RKBIN_DDR_SHA256=\"${DQ08_RKBIN_DDR_SHA256}\"" \
	"DQ08_RKBIN_BL31_SHA256=\"${DQ08_RKBIN_BL31_SHA256}\"" \
	"DQ08_UBOOT_COMMIT=\"${DQ08_UBOOT_COMMIT}\""; do
	if ! grep -Fq "${expected_assignment}" "${extension_file}"; then
		printf 'Extension metadata mismatch: expected %s\n' "${expected_assignment}" >&2
		errors=$((errors + 1))
	fi
done

bcm_firmware_metadata=(
	"DQ08_BCM4335_FIRMWARE_COMMIT=${DQ08_BCM4335_FIRMWARE_COMMIT}"
	"DQ08_BCM4335_WIFI_SHA256=${DQ08_BCM4335_WIFI_SHA256}"
	"DQ08_BCM4335_NVRAM_SHA256=${DQ08_BCM4335_NVRAM_SHA256}"
	"DQ08_BCM4335_BT_A0_SHA256=${DQ08_BCM4335_BT_A0_SHA256}"
	"DQ08_BCM4335_BT_B0_SHA256=${DQ08_BCM4335_BT_B0_SHA256}"
	"DQ08_BCM4335_BT_C0_SHA256=${DQ08_BCM4335_BT_C0_SHA256}"
)
for metadata_assignment in "${bcm_firmware_metadata[@]}"; do
	metadata_var="${metadata_assignment%%=*}"
	expected_value="${metadata_assignment#*=}"
	actual_value="$(sed -n "s/^declare -g ${metadata_var}=\"\\([^\"]*\\)\"$/\\1/p" "${extension_file}")"
	if [[ "${actual_value}" != "${expected_value}" ]]; then
		printf 'BCM4335 firmware metadata mismatch: %s is %s, expected %s\n' \
			"${metadata_var}" "${actual_value:-<missing>}" "${expected_value}" >&2
		errors=$((errors + 1))
	fi
done
if ! grep -Fq '"https://github.com/LibreELEC/brcmfmac_sdio-firmware.git"' "${extension_file}" ||
	! grep -Fq '"commit:${DQ08_BCM4335_FIRMWARE_COMMIT}"' "${extension_file}"; then
	printf 'BCM4335 firmware source is not fetched from the pinned repository commit.\n' >&2
	errors=$((errors + 1))
fi
for bcm_hook in \
	'function fetch_sources_tools__vontar_dq08_bcm4335_firmware() {' \
	'function post_family_tweaks_bsp__vontar_dq08_assets() {' \
	'function pre_umount_final_image__vontar_dq08_verify_bcm4335() {'; do
	if ! grep -Fq "${bcm_hook}" "${extension_file}"; then
		printf 'Required BCM4335 build hook is missing: %s\n' "${bcm_hook}" >&2
		errors=$((errors + 1))
	fi
done

board_file="${module_root}/config/boards/vontar-dq08.csc"
if ! grep -Fq "BOARD_MAINTAINER=\"${DQ08_MAINTAINER}\"" "${board_file}"; then
	printf 'Board maintainer does not match module.conf.\n' >&2
	errors=$((errors + 1))
fi
if ! grep -Fq 'BOARD_FIRMWARE_INSTALL=""' "${board_file}"; then
	printf 'Board does not explicitly select the lean Armbian firmware bundle.\n' >&2
	errors=$((errors + 1))
fi
if ! grep -Fq 'BOOTSIZE="256"' "${board_file}"; then
	printf 'Board boot partition is not the validated 256 MiB size.\n' >&2
	errors=$((errors + 1))
fi
package_list_board="$(sed -n 's/^PACKAGE_LIST_BOARD="\([^"]*\)".*/\1/p' "${board_file}")"
if [[ " ${package_list_board} " != *" iw "* ]]; then
	printf 'Board package list does not explicitly install iw.\n' >&2
	errors=$((errors + 1))
fi

extension_array_has_quoted_item() {
	local array_name="$1"
	local item="$2"

	awk -v array_name="${array_name}" -v needle="\"${item}\"" '
		index($0, array_name "+=(") || index($0, array_name "=(") {
			in_array = 1
			seen_array = 1
			next
		}
		in_array && /^[[:space:]]*\)[[:space:]]*$/ {
			in_array = 0
			next
		}
		in_array {
			line = $0
			sub(/^[[:space:]]+/, "", line)
			sub(/[[:space:]]+$/, "", line)
			if (line == needle)
				found = 1
		}
		END {
			exit seen_array && found ? 0 : 1
		}
	' "${extension_file}"
}

for wifi_kernel_option in \
	BRCMFMAC_PROTO_BCDC \
	BRCMFMAC_SDIO \
	BT_HCIUART_BCM \
	BT_HCIUART_H4 \
	BT_HCIUART_SERDEV \
	FW_LOADER \
	MMC \
	MMC_DW \
	MMC_DW_ROCKCHIP \
	PM \
	PWRSEQ_SIMPLE \
	REGULATOR_FIXED_VOLTAGE \
	SERIAL_DEV_BUS \
	WLAN \
	WLAN_VENDOR_BROADCOM; do
	if ! extension_array_has_quoted_item "opts_y" "${wifi_kernel_option}"; then
		printf 'BCM4335 built-in kernel option is not enforced: %s\n' "${wifi_kernel_option}" >&2
		errors=$((errors + 1))
	fi
done

for wifi_kernel_module_option in \
	BRCMFMAC \
	BRCMUTIL \
	BT \
	BT_BCM \
	BT_HCIUART \
	CFG80211 \
	RFKILL; do
	if ! extension_array_has_quoted_item "opts_m" "${wifi_kernel_module_option}"; then
		printf 'BCM4335 module kernel option is not enforced: %s\n' "${wifi_kernel_module_option}" >&2
		errors=$((errors + 1))
	fi
done

extension_install_list_has_file() {
	local basename="$1"

	awk -v needle="${basename}" '
		/^[[:space:]]*for relative_path in[[:space:]]*\\[[:space:]]*$/ {
			in_list = 1
			next
		}
		in_list {
			line = $0
			sub(/^[[:space:]]+/, "", line)
			sub(/[[:space:]]*\\[[:space:]]*$/, "", line)
			sub(/[[:space:]]*;[[:space:]]*do[[:space:]]*$/, "", line)
			if (line == needle)
				found = 1
			if ($0 ~ /;[[:space:]]*do[[:space:]]*$/)
				in_list = 0
		}
		END {
			exit found ? 0 : 1
		}
	' "${extension_file}"
}

bcm_image_firmware=(
	"brcm/brcmfmac4335-sdio.bin=DQ08_BCM4335_WIFI_SHA256"
	"brcm/brcmfmac4335-sdio.txt=DQ08_BCM4335_NVRAM_SHA256"
	"brcm/BCM4335A0.hcd=DQ08_BCM4335_BT_A0_SHA256"
	"brcm/BCM4335B0.hcd=DQ08_BCM4335_BT_B0_SHA256"
	"brcm/BCM4335C0.hcd=DQ08_BCM4335_BT_C0_SHA256"
)
for firmware_assignment in "${bcm_image_firmware[@]}"; do
	relative_path="${firmware_assignment%%=*}"
	hash_var="${firmware_assignment#*=}"
	basename="${relative_path##*/}"
	printf -v source_validation_fragment '["%s"]="${%s}"' "${basename}" "${hash_var}"
	if ! grep -Fq "${source_validation_fragment}" "${extension_file}"; then
		printf 'BCM4335 source hash validation is missing: %s\n' "${basename}" >&2
		errors=$((errors + 1))
	fi
	printf -v validation_fragment '["%s"]="${%s}"' "${relative_path}" "${hash_var}"
	if ! grep -Fq "${validation_fragment}" "${extension_file}"; then
		printf 'BCM4335 final-image hash validation is missing: %s\n' "${relative_path}" >&2
		errors=$((errors + 1))
	fi
	if ! extension_install_list_has_file "${basename}"; then
		printf 'BCM4335 firmware installation is missing: %s\n' "${basename}" >&2
		errors=$((errors + 1))
	fi
done

extension_has_firmware_link() {
	local link_name="$1"
	local link_target="$2"

	awk \
		-v expected_source="\"${link_target}\"" \
		-v expected_destination="\"\${firmware_target}/${link_name}\"" \
		-v readlink_name="/brcm/${link_name}\"" \
		-v expected_readlink="\"${link_target}\" ]]" '
		function clean_command_argument(line) {
			sub(/^[[:space:]]+/, "", line)
			sub(/[[:space:]]*\\[[:space:]]*$/, "", line)
			sub(/[[:space:]]+$/, "", line)
			return line
		}
		/run_host_command_logged ln -sf[[:space:]]*\\[[:space:]]*$/ {
			if ((getline source_line) > 0 && (getline destination_line) > 0 &&
				clean_command_argument(source_line) == expected_source &&
				clean_command_argument(destination_line) == expected_destination)
				installs_link = 1
		}
		index($0, readlink_name) {
			if ((getline target_line) > 0 &&
				index(clean_command_argument(target_line), expected_readlink) == 1)
				validates_link = 1
		}
		END {
			exit installs_link && validates_link ? 0 : 1
		}
	' "${extension_file}"
}

for firmware_link in \
	'brcmfmac4335-sdio.vontar,dq08.bin=brcmfmac4335-sdio.bin' \
	'brcmfmac4335-sdio.vontar,dq08.txt=brcmfmac4335-sdio.txt'; do
	link_name="${firmware_link%%=*}"
	link_target="${firmware_link#*=}"
	if ! extension_has_firmware_link "${link_name}" "${link_target}"; then
		printf 'BCM4335 board-specific firmware link validation is missing: %s -> %s\n' \
			"${link_name}" "${link_target}" >&2
		errors=$((errors + 1))
	fi
done

for wifi_module in brcmfmac brcmutil btbcm cfg80211 hci_uart; do
	if ! extension_array_has_quoted_item "kernel_modules" "${wifi_module}"; then
		printf 'BCM4335 final-image module validation is missing: %s\n' "${wifi_module}" >&2
		errors=$((errors + 1))
	fi
done

dts_file="${module_root}/kernel/archive/rockchip64-${DQ08_KERNEL_SERIES}/dt/rk3528-vontar-dq08.dts"
for wifi_dts_property in \
	'compatible = "mmc-pwrseq-simple";' \
	'reset-gpios = <&gpio3 RK_PB4 GPIO_ACTIVE_LOW>;' \
	'gpios = <&gpio3 RK_PB2 GPIO_ACTIVE_HIGH>;' \
	'&sdio1 {' \
	'cap-sdio-irq;' \
	'mmc-pwrseq = <&sdio_pwrseq>;' \
	'bcm4335: wifi@1 {' \
	'compatible = "brcm,bcm4335-fmac", "brcm,bcm4329-fmac";' \
	'interrupts = <RK_PB3 IRQ_TYPE_LEVEL_HIGH>;' \
	'interrupt-names = "host-wake";' \
	'&uart2 {' \
	'uart-has-rtscts;' \
	'compatible = "brcm,bcm4335a0";' \
	'interrupt-names = "host-wakeup";' \
	'shutdown-gpios = <&gpio3 RK_PC2 GPIO_ACTIVE_HIGH>;'; do
	if ! grep -Fq "${wifi_dts_property}" "${dts_file}"; then
		printf 'BCM4335 device-tree wiring is missing: %s\n' "${wifi_dts_property}" >&2
		errors=$((errors + 1))
	fi
done
if ! grep -Eq 'interrupts = <RK_PC1 IRQ_TYPE_(EDGE_RISING|LEVEL_HIGH)>;' "${dts_file}"; then
	printf 'BCM4335 Bluetooth host-wakeup IRQ wiring is missing or has an invalid trigger.\n' >&2
	errors=$((errors + 1))
fi

for implementation_file in "${board_file}" "${extension_file}" "${dts_file}"; do
	if stale_realtek="$(grep -Einm1 \
		'rtl8822cs|rtw88|WLAN_VENDOR_REALTEK|realtek,rtl' "${implementation_file}")"; then
		printf 'Stale RTL8822CS implementation remains in %s: %s\n' \
			"${implementation_file}" "${stale_realtek}" >&2
		errors=$((errors + 1))
	fi
done

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
