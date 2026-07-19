#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

# Match the exact public Rockchip binaries pinned by fensoft/dq08-haos.
declare -g DQ08_RKBIN_COMMIT="f43a462e7a1429a9d407ae52b4745033034a6cf9"
declare -g DQ08_RKBIN_DIR="${SRC}/cache/sources/vontar-dq08-rkbin"
declare -g DDR_BLOB="bin/rk35/rk3528_ddr_1056MHz_4BIT_PCB_v1.10.bin"
declare -g BL31_BLOB="bin/rk35/rk3528_bl31_v1.18.elf"
declare -g UBOOT_HASH_EXTRA="vontar-dq08-rkbin-${DQ08_RKBIN_COMMIT}"

function fetch_sources_tools__vontar_dq08_rkbin() {
	fetch_from_repo "https://github.com/rockchip-linux/rkbin.git" "vontar-dq08-rkbin" "commit:${DQ08_RKBIN_COMMIT}"
}

function post_family_config__vontar_dq08_mainline_uboot() {
	display_alert "$BOARD" "Using upstream U-Boot v2026.04" "info"
	declare -g BOOTSOURCE="https://github.com/u-boot/u-boot.git"
	declare -g BOOTBRANCH="tag:v2026.04"
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
	local dq08_bsp_assets_version="1"
	local assets_root="${EXTENSION_DIR}/files"
	local service="dq08-front-panel.service"
	local wants="${destination}/etc/systemd/system/multi-user.target.wants"

	[[ -d "${assets_root}" ]] || exit_with_error "DQ08 extension assets are missing" "${assets_root}"
	display_alert "$BOARD" "Installing DQ08 BSP assets v${dq08_bsp_assets_version}" "info"
	run_host_command_logged cp -a "${assets_root}/." "${destination}/"
	run_host_command_logged mkdir -p "${wants}"
	run_host_command_logged ln -sf "/usr/lib/systemd/system/${service}" "${wants}/${service}"
}
