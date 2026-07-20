# SPDX-License-Identifier: GPL-2.0-or-later
# Rockchip RK3528, 4-bit LPDDR4, GBe, eMMC, microSD, USB3, Wi-Fi/BT, IR, front display
BOARD_NAME="Vontar DQ08"
BOARD_VENDOR="vontar"
BOARDFAMILY="rk35xx"
BOOTCONFIG="generic-rk3528_defconfig"
BOARD_MAINTAINER="fensoft"
INTRODUCED="2023"
KERNEL_TARGET="current"
KERNEL_TEST_TARGET="current"
FULL_DESKTOP="no"
HAS_VIDEO_OUTPUT="no"
BOOT_FDT_FILE="rockchip/rk3528-vontar-dq08.dtb"
BOOT_SCENARIO="binman"
IMAGE_PARTITION_TABLE="gpt"
BOOTFS_TYPE="ext4"
BOOTSIZE="512"
SERIALCON="ttyS0"

# Install the complete firmware bundle for the RTL8822CS Wi-Fi/Bluetooth module.
BOARD_FIRMWARE_INSTALL="-full"
PACKAGE_LIST_BOARD="i2c-tools ir-keytable python3-minimal rfkill bluetooth bluez bluez-tools"

# All procedural support and rootfs assets live in this module's extension.
enable_extension "dq08-bsp"
