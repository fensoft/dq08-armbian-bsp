#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

# Match the exact public Rockchip binaries pinned by fensoft/dq08-haos.
declare -g DQ08_RKBIN_COMMIT="f43a462e7a1429a9d407ae52b4745033034a6cf9"
declare -g DQ08_RKBIN_DDR_SHA256="f404365dd3929481052548c220aff3e82238bc7a679f13ab52e7e4e9ca1cfeb4"
declare -g DQ08_RKBIN_BL31_SHA256="3dde96556de969c92784e0f37b50a696bd457200353bbb611a91130b0ef960b9"
declare -g DQ08_UBOOT_COMMIT="88dc2788777babfd6322fa655df549a019aa1e69"
declare -g DQ08_RKBIN_DIR="${SRC}/cache/sources/vontar-dq08-rkbin"
declare -g DQ08_BCM4335_FIRMWARE_COMMIT="5987820e4ff88a5626536f66257165fe3a781b73"
declare -g DQ08_BCM4335_WIFI_SHA256="1551fd7680db31d230c70f55860ca071331a37eeb54c9229307b8fa475f9d6e7"
declare -g DQ08_BCM4335_NVRAM_SHA256="dbe8e44633ac69027cfb7a7f094681578b18415f7b74fe5b033eb34d140891af"
declare -g DQ08_BCM4335_BT_A0_SHA256="3e14e7f3c02e19408c5783f845329309e23305ab5f33fb19abfd24a73a84cd8a"
declare -g DQ08_BCM4335_FIRMWARE_DIR="${SRC}/cache/sources/vontar-dq08-brcmfmac-sdio-firmware"
declare -g DDR_BLOB="bin/rk35/rk3528_ddr_1056MHz_4BIT_PCB_v1.10.bin"
declare -g BL31_BLOB="bin/rk35/rk3528_bl31_v1.18.elf"
declare -g UBOOT_HASH_EXTRA="vontar-dq08-rkbin-${DQ08_RKBIN_COMMIT}"

# Do not rely on Armbian's global rockchip64 defconfig to keep the on-board
# HK2735M/BCM4335 enabled. The arrays are consumed in both kernel-config phases:
# first for artifact hashing, then for applying the options to .config.
function custom_kernel_config__vontar_dq08_bcm4335() {
	opts_y+=(
		"BRCMFMAC_PROTO_BCDC"
		"BRCMFMAC_SDIO"
		"BT_HCIUART_BCM"
		"BT_HCIUART_H4"
		"BT_HCIUART_SERDEV"
		"FW_LOADER"
		"MMC"
		"MMC_DW"
		"MMC_DW_ROCKCHIP"
		"PM"
		"PWRSEQ_SIMPLE"
		"REGULATOR_FIXED_VOLTAGE"
		"SERIAL_DEV_BUS"
		"SERIAL_DEV_CTRL_TTYPORT"
		"WLAN"
		"WLAN_VENDOR_BROADCOM"
	)
	opts_m+=(
		"BRCMFMAC"
		"BRCMUTIL"
		"BT"
		"BT_BCM"
		"BT_HCIUART"
		"CFG80211"
		"RFKILL"
	)
}

function dq08_fetch_and_verify_bcm4335_firmware() {
	fetch_from_repo \
		"https://github.com/LibreELEC/brcmfmac_sdio-firmware.git" \
		"vontar-dq08-brcmfmac-sdio-firmware" \
		"commit:${DQ08_BCM4335_FIRMWARE_COMMIT}"

	local actual_sha256 relative_path
	local -A expected_sha256=(
		["brcmfmac4335-sdio.bin"]="${DQ08_BCM4335_WIFI_SHA256}"
	)

	for relative_path in "${!expected_sha256[@]}"; do
		actual_sha256="$(sha256sum "${DQ08_BCM4335_FIRMWARE_DIR}/${relative_path}" | awk '{print $1}')"
		[[ "${actual_sha256}" == "${expected_sha256["${relative_path}"]}" ]] ||
			exit_with_error "DQ08 BCM4335 firmware checksum mismatch" "${relative_path}"
	done
}

function fetch_sources_tools__vontar_dq08_bcm4335_firmware() {
	dq08_fetch_and_verify_bcm4335_firmware
}

function fetch_sources_tools__vontar_dq08_rkbin() {
	fetch_from_repo "https://github.com/rockchip-linux/rkbin.git" "vontar-dq08-rkbin" "commit:${DQ08_RKBIN_COMMIT}"

	local ddr_sha256 bl31_sha256
	ddr_sha256="$(sha256sum "${DQ08_RKBIN_DIR}/${DDR_BLOB}" | awk '{print $1}')"
	bl31_sha256="$(sha256sum "${DQ08_RKBIN_DIR}/${BL31_BLOB}" | awk '{print $1}')"
	[[ "${ddr_sha256}" == "${DQ08_RKBIN_DDR_SHA256}" ]] || exit_with_error "DQ08 DDR blob checksum mismatch" "${DDR_BLOB}"
	[[ "${bl31_sha256}" == "${DQ08_RKBIN_BL31_SHA256}" ]] || exit_with_error "DQ08 BL31 blob checksum mismatch" "${BL31_BLOB}"
}

function post_family_config__vontar_dq08_mainline_uboot() {
	display_alert "$BOARD" "Using upstream U-Boot v2026.04" "info"
	declare -g BOOTSOURCE="https://github.com/u-boot/u-boot.git"
	declare -g BOOTBRANCH="commit:${DQ08_UBOOT_COMMIT}"
	declare -g BOOTPATCHDIR="v2026.04"
	declare -g UBOOT_TARGET_MAP="BL31=${DQ08_RKBIN_DIR}/${BL31_BLOB} ROCKCHIP_TPL=${DQ08_RKBIN_DIR}/${DDR_BLOB};;u-boot-rockchip.bin"
}

function post_config_uboot_target__vontar_dq08_i2c_preboot() {
	display_alert "$BOARD" "Enabling I2C1 and DQ08 front-panel preboot initialization" "info"
	run_host_command_logged scripts/config --enable CONFIG_USE_PREBOOT
	run_host_command_logged scripts/config --set-str CONFIG_PREBOOT "'i2c dev 0; i2c mw 0x24 0x00 0x31; i2c mw 0x34 0x7c 0x5c; i2c mw 0x36 0x5c 0x78'"
	run_host_command_logged scripts/config --enable CONFIG_DM_I2C
	run_host_command_logged scripts/config --enable CONFIG_CMD_I2C
	run_host_command_logged scripts/config --enable CONFIG_SYS_I2C_ROCKCHIP
}

# boot-rk35xx.cmd defaults to ttyS2, while RK3528's debug UART is UART0.
function post_family_tweaks__vontar_dq08_serial_console() {
	display_alert "$BOARD" "Adjusting boot.cmd serial console to ttyS0" "info"
	sed -i 's/console=ttyS2,1500000/console=ttyS0,1500000/g' "${SDCARD}/boot/boot.cmd"
	mkimage -C none -A arm -T script -d "${SDCARD}/boot/boot.cmd" "${SDCARD}/boot/boot.scr"
}

function post_family_tweaks_bsp__vontar_dq08_assets() {
	: "${destination:?destination is not set}"
	: "${EXTENSION_DIR:?EXTENSION_DIR is not set}"

	# Bump this literal whenever anything below files/ changes. The hook body
	# is included in Armbian's BSP package cache key; extension assets are not.
	local dq08_bsp_assets_version="9"
	local assets_root="${EXTENSION_DIR}/files"
	local firmware_target="${destination}/usr/lib/firmware/brcm"
	local nvram_source="${assets_root}/usr/lib/firmware/brcm/brcmfmac4335-sdio.txt"
	local hcd_source="${assets_root}/usr/lib/firmware/brcm/BCM4335A0.hcd"
	local packaged_boot_cmd="${destination}/usr/share/armbian/boot.cmd"
	local service="dq08-front-panel.service"
	local wants="${destination}/etc/systemd/system/multi-user.target.wants"
	local actual_sha256 relative_path source_file
	local -A local_expected_sha256=(
		["BCM4335A0.hcd"]="${DQ08_BCM4335_BT_A0_SHA256}"
		["brcmfmac4335-sdio.txt"]="${DQ08_BCM4335_NVRAM_SHA256}"
	)

	[[ -d "${assets_root}" ]] || exit_with_error "DQ08 extension assets are missing" "${assets_root}"
	for source_file in "${nvram_source}" "${hcd_source}"; do
		relative_path="${source_file##*/}"
		actual_sha256="$(sha256sum "${source_file}" | awk '{print $1}')"
		[[ "${actual_sha256}" == "${local_expected_sha256["${relative_path}"]}" ]] ||
			exit_with_error "DQ08 factory BCM4335 payload checksum mismatch" "${source_file}"
	done
	# fetch_sources_tools is normally reached through the U-Boot artifact.  A
	# cached U-Boot can let bsp-cli run first, so make this consumer
	# independently safe instead of relying on artifact build order.
	dq08_fetch_and_verify_bcm4335_firmware
	display_alert "$BOARD" "Installing DQ08 BSP assets v${dq08_bsp_assets_version}" "info"
	run_host_command_logged cp -a "${assets_root}/." "${destination}/"
	[[ -f "${packaged_boot_cmd}" ]] ||
		exit_with_error "DQ08 packaged boot script is missing" "${packaged_boot_cmd}"
	# Keep the BSP package's recovery/upgrade source in sync with the live
	# image.  Otherwise recreating a missing /boot/boot.cmd restores ttyS2.
	run_host_command_logged sed -i \
		's/console=ttyS2,1500000/console=ttyS0,1500000/g' \
		"${packaged_boot_cmd}"
	grep -Fq 'console=ttyS0,1500000' "${packaged_boot_cmd}" ||
		exit_with_error "DQ08 packaged boot script still has the wrong console" "${packaged_boot_cmd}"
	run_host_command_logged install -d -m 0755 "${firmware_target}"
	for relative_path in \
		brcmfmac4335-sdio.bin \
		brcmfmac4335-sdio.txt \
		BCM4335A0.hcd; do
		source_file="${DQ08_BCM4335_FIRMWARE_DIR}/${relative_path}"
		if [[ "${relative_path}" == "brcmfmac4335-sdio.txt" ]]; then
			source_file="${nvram_source}"
		elif [[ "${relative_path}" == "BCM4335A0.hcd" ]]; then
			source_file="${hcd_source}"
		fi
		run_host_command_logged install -m 0644 \
			"${source_file}" \
			"${firmware_target}/${relative_path}"
	done
	run_host_command_logged ln -sf \
		"brcmfmac4335-sdio.bin" \
		"${firmware_target}/brcmfmac4335-sdio.vontar,dq08.bin"
	run_host_command_logged ln -sf \
		"brcmfmac4335-sdio.txt" \
		"${firmware_target}/brcmfmac4335-sdio.vontar,dq08.txt"
	run_host_command_logged mkdir -p "${wants}"
	run_host_command_logged ln -sf "/usr/lib/systemd/system/${service}" "${wants}/${service}"
}

# Catch a kernel or firmware packaging regression before publishing or flashing
# an image. SDIO loads Wi-Fi by modalias; modules-load.d starts the UART transport.
function pre_umount_final_image__vontar_dq08_verify_bcm4335() {
	: "${MOUNT:?MOUNT is not set}"

	local firmware_root="${MOUNT}/usr/lib/firmware"
	local modules_root="${MOUNT}/usr/lib/modules"
	local modules_load="${MOUNT}/etc/modules-load.d/vontar-dq08-bluetooth.conf"
	local active_boot_cmd="${MOUNT}/boot/boot.cmd"
	local packaged_boot_cmd="${MOUNT}/usr/share/armbian/boot.cmd"
	local actual_sha256 relative_path module_name module_path
	local -a missing=()
	local -A expected_sha256=(
		["brcm/brcmfmac4335-sdio.bin"]="${DQ08_BCM4335_WIFI_SHA256}"
		["brcm/brcmfmac4335-sdio.txt"]="${DQ08_BCM4335_NVRAM_SHA256}"
		["brcm/BCM4335A0.hcd"]="${DQ08_BCM4335_BT_A0_SHA256}"
	)
	local -a kernel_modules=(
		"brcmfmac"
		"brcmutil"
		"btbcm"
		"cfg80211"
		"hci_uart"
	)

	for relative_path in "${!expected_sha256[@]}"; do
		if [[ ! -s "${firmware_root}/${relative_path}" ]]; then
			missing+=("firmware:${relative_path}")
			continue
		fi
		actual_sha256="$(sha256sum "${firmware_root}/${relative_path}" | awk '{print $1}')"
		[[ "${actual_sha256}" == "${expected_sha256["${relative_path}"]}" ]] ||
			missing+=("checksum:${relative_path}")
	done

	[[ "$(readlink "${firmware_root}/brcm/brcmfmac4335-sdio.vontar,dq08.bin" 2> /dev/null || true)" == \
		"brcmfmac4335-sdio.bin" ]] || missing+=("firmware:board-specific-bin-link")
	[[ "$(readlink "${firmware_root}/brcm/brcmfmac4335-sdio.vontar,dq08.txt" 2> /dev/null || true)" == \
		"brcmfmac4335-sdio.txt" ]] || missing+=("firmware:board-specific-nvram-link")
	for module_name in "${kernel_modules[@]}"; do
		module_path="$(find "${modules_root}" -type f -name "${module_name}.ko*" -print -quit 2> /dev/null || true)"
		[[ -n "${module_path}" ]] || missing+=("module:${module_name}")
	done
	grep -Eq '^[[:space:]]*hci_uart([[:space:]]*(#.*)?)?$' "${modules_load}" 2> /dev/null ||
		missing+=("modules-load:hci_uart")
	grep -Fq 'console=ttyS0,1500000' "${active_boot_cmd}" 2> /dev/null ||
		missing+=("boot-script:active-ttyS0")
	grep -Fq 'console=ttyS0,1500000' "${packaged_boot_cmd}" 2> /dev/null ||
		missing+=("boot-script:packaged-ttyS0")
	if grep -Fq 'console=ttyS2,1500000' "${active_boot_cmd}" 2> /dev/null ||
		grep -Fq 'console=ttyS2,1500000' "${packaged_boot_cmd}" 2> /dev/null; then
		missing+=("boot-script:stale-ttyS2")
	fi

	if ((${#missing[@]})); then
		exit_with_error "DQ08 HK2735M wireless support is incomplete" "${missing[*]}"
	fi

	display_alert "${BOARD}" "Validated HK2735M modules and pinned firmware" "info"
}
