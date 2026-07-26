# Vontar DQ08 Armbian BSP module — full reference

This repository is a portable Armbian **userpatches module** for the Vontar
DQ08 TV box (Rockchip RK3528). It packages the board description, Linux device
tree, U-Boot patch and boot configuration, pinned Rockchip DDR/BL31 firmware
selection, infrared keymap, and front-panel service.

It builds a normal headless Armbian image. It does not install Home Assistant,
and it is not a Linux loadable kernel module (.ko).

## Status

The module is pinned to Armbian's supported **current** kernel line, Linux
6.18. It does not select a legacy/vendor kernel.

| Component | Tested version |
| --- | --- |
| Armbian build | 90fda43901b0127104227975ae62d35fbad05abc |
| Linux | 6.18.39 at f89c296854b755a66657065c35b05406fc18264d |
| U-Boot | v2026.04 at 88dc2788777babfd6322fa655df549a019aa1e69 |
| Rockchip rkbin | f43a462e7a1429a9d407ae52b4745033034a6cf9 |
| BCM4335 Wi-Fi firmware | LibreELEC/brcmfmac_sdio-firmware at 5987820e4ff88a5626536f66257165fe3a781b73 |
| BCM4335A0 Bluetooth HCD | Official Vontar DQ08 factory payload, SHA-256 `3e14e7f3c02e19408c5783f845329309e23305ab5f33fb19abfd24a73a84cd8a` |
| Source BSP | fensoft/dq08-haos at ebc35462a307fad483a7ea0f01b05cbc2b17d458 |

The device tree covers eMMC, microSD, Ethernet, USB, HK2735M wireless,
infrared input, the power LED, serial console, and the I2C front panel. The
target module is BCM4335 Wi-Fi plus BCM4335A0 Bluetooth. Linux reports SDIO
vendor `0x02d0`, device `0x4335`; the UART controller reports Broadcom
manufacturer `0x000f`, LMP subversion `0x4106`, and local name `BCM4335A0`.
The earlier RTL8822CS assumption came from a misleading vendor device-tree
label and does not describe this HK2735M PCB variant.

The BSP selects the upstream `brcmfmac` SDIO driver and Broadcom HCI UART
support. It retains the lean `armbian-firmware` package, avoiding the roughly
2.2 GiB installed generic firmware bundle. During every build it fetches the
exact LibreELEC firmware commit listed above and verifies SHA-256 before use.
It combines the public `brcmfmac4335-sdio.bin` with the factory DQ08
`nvram_bcm4335.txt` calibration for the SEMCO B62_G3/4335B0 module. The NVRAM
is committed as text with only a normalized final newline; its RF parameters
otherwise match the factory payload. Using the former Murata Type-XJ NVRAM was
incorrect for this PCB.

The build commits the exact official `BCM4335A0.hcd` extracted from the DQ08
factory image. Its SHA-256 is pinned, and it is byte-identical to the public
LibreELEC copy. Only the proven A0 payload is installed: Linux 6.18 maps the
controller's `0x4106` subversion directly to `BCM4335A0.hcd`. Board-specific
`vontar,dq08` links point at the selected Wi-Fi firmware and factory-derived
NVRAM. The Broadcom binary license is included alongside the firmware. The
final-image hook verifies the files, hashes, links, and required kernel
modules; runtime scans provide the hardware gate.

Bluetooth bootstrap holds PC2 BT_REG_ON low while driving PC1 HOST_WAKE high
for 40 ms, raises PC2, holds PC1 high for another 20 ms, returns PC1 to input,
and settles for 150 ms. UART2 then operates at 115200 bit/s with hardware
CRTSCTS. The BSP deliberately omits the legacy PA2/RTS GPIO pulse: direct raw
UART tests proved that HCI Reset succeeds without it and fails after it.

UART2 uses Linux 6.18's corrected RK3528 DMA request order, inherited from
`rk3528.dtsi` as TX channel 13 and RX channel 12, with the required
`dma-names = "tx", "rx"` supplied by the board DTS. Mainline fixed that order
after the ArmSoM Sige1 showed the same `0x0c03` HCI Reset timeout and Broadcom
`Reset failed (-110)` result. The vendor 5.10 tree's `!tx`/`!rx` PIO choice is
therefore not carried forward.

The corrected DMA mapping, no-RTS-pulse bootstrap, A0 HCD load, controller
creation, and bounded Bluetooth scan were validated on the DQ08. Wi-Fi
firmware initialization, interface creation, and nearby-network scanning were
validated separately.

The boot partition is 256 MiB; the corrected software-validated build uses
about 111 MB of its 224 MiB formatted capacity. The board is deliberately
marked headless: upstream Linux 6.18
does not provide the old vendor multimedia stack used by the legacy BSP, so
HDMI, audio, VPU, and GPU acceleration are outside this module's supported
scope.

With Bookworm, Linux 6.18.39, and XZ level 1, the lean-firmware build is about
2.0 GiB raw and 399 MiB compressed. Use the generated `.img.xz.sha` file for
the exact hash of each build. The earlier full-firmware build required a
4,676 MiB raw image and compressed to about 1.13 GiB.

## Repository layout

~~~
config/boards/
  vontar-dq08.csc              Armbian board definition

extensions/dq08-bsp/
  dq08-bsp.sh                  Armbian build hooks
  files/                       Files copied into the target root filesystem

kernel/archive/rockchip64-6.18/
  dq08-bluetooth-factory-bootstrap.patch
                                 Board-only hci_bcm startup sequence
  dt/rk3528-vontar-dq08.dts    Linux device tree

u-boot/v2026.04/
  board_vontar-dq08/           U-Boot patches

install.sh                     Install into an Armbian checkout
uninstall.sh                   Remove only files managed by this module
build.sh                       Install and build a minimal image
verify.sh                      Check the module and an optional installation
manifest.txt                   Exact list of managed userpatches files
module.conf                    Tested versions and module metadata
scripts/ci/                    Release discovery, build, and validation helpers
infra/oci/                     OpenTofu stack for the ARM64 build runner
~~~

The paths listed in manifest.txt are copied below
armbian-build/userpatches/. Nothing in Armbian's tracked config/ or patch/
trees is changed.

## Host requirements

Use a 64-bit Linux host with Git and Docker installed. Armbian's build
container supplies the compiler and remaining build dependencies. Expect the
first build to download several gigabytes and take a while.

On Debian or Ubuntu:

~~~
sudo apt update
sudo apt install git docker.io
sudo usermod -aG docker "$USER"
~~~

Log out and back in after adding yourself to the docker group, or run the build
with a Docker setup that your account can access.

## Quick start

Clone the tested Armbian revision and this module as sibling directories:

~~~
git clone https://github.com/armbian/build.git armbian-build
git -C armbian-build checkout --detach 90fda43901b0127104227975ae62d35fbad05abc

git clone YOUR_GIT_URL dq08-armbian-bsp

./dq08-armbian-bsp/verify.sh
./dq08-armbian-bsp/install.sh ./armbian-build
./dq08-armbian-bsp/verify.sh ./armbian-build
./dq08-armbian-bsp/build.sh ./armbian-build bookworm
~~~

The build wrapper installs the module, then requests:

- board vontar-dq08;
- current Linux, which is 6.18 at the tested Armbian revision;
- a minimal, non-desktop image;
- Docker-based compilation;
- Debian Bookworm by default.

The image appears in:

~~~
armbian-build/output/images/
~~~

A tested filename is:

~~~
Armbian-unofficial_26.08.0-trunk_Vontar-dq08_bookworm_current_6.18.39_minimal.img
~~~

Armbian's release label may differ on a later checkout.

## Install and compile manually

Installing is safe for an Armbian tree that already has other userpatches.
Only manifest entries are managed. Different existing files are treated as
conflicts and are not overwritten unless --force is supplied.

Preview the installation:

~~~
./dq08-armbian-bsp/install.sh --dry-run ./armbian-build
~~~

Install it:

~~~
./dq08-armbian-bsp/install.sh ./armbian-build
~~~

Inspect Armbian's resolved configuration without compiling:

~~~
cd armbian-build

./compile.sh config-dump \
  BOARD=vontar-dq08 \
  BRANCH=current \
  RELEASE=bookworm \
  BUILD_MINIMAL=yes \
  BUILD_DESKTOP=no \
  KERNEL_CONFIGURE=no \
  PREFER_DOCKER=yes
~~~

The dump should include KERNEL_MAJOR_MINOR=6.18,
BOOT_FDT_FILE=rockchip/rk3528-vontar-dq08.dtb, U-Boot v2026.04, and the
dq08-bsp extension.

Build the image:

~~~
./compile.sh build \
  BOARD=vontar-dq08 \
  BRANCH=current \
  RELEASE=bookworm \
  BUILD_MINIMAL=yes \
  BUILD_DESKTOP=no \
  KERNEL_CONFIGURE=no \
  PREFER_DOCKER=yes
~~~

PREFER_DOCKER=yes is a configuration option. Do not append a separate
"docker" action to the command.

The wrapper accepts another release and extra Armbian key/value options:

~~~
./dq08-armbian-bsp/build.sh ./armbian-build trixie \
  COMPRESS_OUTPUTIMAGE=sha,img
~~~

Whether a release is buildable depends on the checked-out Armbian revision.
By default, Armbian follows the newest stable 6.18.y commit available to that
revision. To reproduce the tested 6.18.39 kernel exactly:

~~~
./dq08-armbian-bsp/build.sh ./armbian-build bookworm \
  KERNELBRANCH=commit:f89c296854b755a66657065c35b05406fc18264d
~~~

## Verify the output

Verify the module before each build:

~~~
./dq08-armbian-bsp/verify.sh ./armbian-build
~~~

Inspect the generated image and checksum:

~~~
cd armbian-build/output/images
sha256sum -c *.img.xz.sha
xz -t *.img.xz
xz --robot --list *.img.xz
~~~

If more than one image exists, name the intended image explicitly instead of
using a wildcard. To inspect the GPT, decompress that image first; this creates
the 2,036 MiB raw file:

~~~
xz -dk Armbian-unofficial_*_Vontar-dq08_*_minimal.img.xz
fdisk -l Armbian-unofficial_*_Vontar-dq08_*_minimal.img
~~~

## Flash a Lexar SD card

Run the flasher on the build host, not on the DQ08. Insert the 64 GB Lexar in
the host reader and identify its whole-disk link without touching its data:

~~~
lsblk -e 7 -o NAME,PATH,TYPE,SIZE,VENDOR,MODEL,SERIAL,RM,RO,MOUNTPOINTS
ls -l /dev/disk/by-id/
~~~

Unmount every target partition manually. The script deliberately refuses any
mounted target and never unmounts one itself. Use the whole-disk `by-id` link,
with no `-partN` suffix:

~~~
IMAGE=armbian-build/output/images/Armbian-unofficial_26.08.0-trunk_Vontar-dq08_bookworm_current_6.18.39_minimal.img.xz
DEVICE=/dev/disk/by-id/usb-Lexar_<device-id>
sudo ./dq08-armbian-bsp/flash.sh "$IMAGE" "$DEVICE"
~~~

The flasher requires the Armbian `${IMAGE}.sha` sidecar produced by
`COMPRESS_OUTPUTIMAGE=sha,xz`. It fails closed unless the target is a writable,
removable whole disk of 55--70 GB whose vendor/model/serial identifies Lexar.
It explicitly rejects the running root-device ancestry, all mounts, swap and
block holders. After displaying the exact model, serial and byte size, it
requires an exact typed confirmation. It tests the XZ stream, writes with
`dd`/`fsync`, flushes device buffers and hashes exactly the uncompressed image
length back from the Lexar; success is reported only when the source and
read-back SHA-256 values match.

The build-time final-image check proves that the expected driver and pinned
files are present. It does not exercise the SDIO bus, radio, antenna, or
Bluetooth UART. After flashing and booting the newly rebuilt image, first
confirm the physical SDIO identity without relying on a device-tree label:

~~~
sdio=/sys/bus/sdio/devices/mmc2:0001:1
cat "$sdio/vendor"
cat "$sdio/device"
cat "$sdio/modalias"
cat "$sdio/uevent"
~~~

Expected identifiers are vendor `0x02d0`, device `0x4335`, and an SDIO modalias
containing `v02D0d4335`. Then inspect driver and firmware initialization:

~~~
journalctl -b -k -o cat --no-pager |
  grep -Ei 'mmc2|sdio|brcmfmac|brcmutil|firmware'
lsmod | grep -E 'brcmfmac|brcmutil|cfg80211'
~~~

A successful initialization includes `brcmfmac4335-sdio` for chip `BCM4335/1`
and a later BCM4335 firmware-version message. A missing board-specific filename
is harmless only if the log subsequently falls back to the generic file and
finishes initialization. Missing generic `.bin` or `.txt` files, a firmware
download timeout, or no wireless interface is a failure. An optional missing
`.clm_blob` warning may restrict channels but does not by itself mean firmware
loading failed.

Exercise the radio rather than treating module loading as sufficient:

~~~
rfkill unblock wifi
wifi_if="$(iw dev | awk '$1 == "Interface" { print $2; exit }')"
test -n "$wifi_if"
ip link set "$wifi_if" up
iw dev "$wifi_if" info
iw dev "$wifi_if" scan | grep -E '^BSS|^[[:space:]]+SSID:'
~~~

Nearby BSS entries prove that the SDIO transport, firmware, NVRAM, radio, and
receive path are functioning. After configuring credentials through the
selected Armbian networking stack, validate end-to-end traffic:

~~~
networkctl status "$wifi_if"
ip -br address show dev "$wifi_if"
ping -I "$wifi_if" -c 5 1.1.1.1
~~~

The default minimal build uses systemd-networkd. `nmcli` applies only when
building with Armbian's NetworkManager stack.

Check Bluetooth separately; Wi-Fi success does not validate the UART side:

~~~
rfkill unblock bluetooth
systemctl enable --now bluetooth
sleep 2
lsmod | grep -E '^(hci_uart|btbcm|bluetooth)'
ls -l /sys/class/bluetooth
journalctl -b -k -o cat --no-pager |
  grep -Ei 'ffa00000|DQ08 Bluetooth|bluetooth|hci_uart|btbcm|BCM4335|firmware'
bluetoothctl list
bluetoothctl show
bluetoothctl power on
timeout 30 bluetoothctl scan on
~~~

`hci_uart` must be present without running `modprobe` manually. A pass has the
DQ08 startup log, a successful `BCM4335A0.hcd` load, no HCI timeout or
`BCM: Reset failed`, a controller from `bluetoothctl list`, and nearby devices
from the bounded scan. This gate passed on the DQ08 with the corrected
no-RTS-pulse module loaded. The Wi-Fi identity, firmware initialization,
interface creation, and nearby-network scan gate passed on the same hardware.

## Firmware provenance

The module commits the factory SEMCO NVRAM and official `BCM4335A0.hcd`, with
the Broadcom license beside them. The HCD came from Vontar's
`RK3528_DC_DQ08_Multi_WIFI_13_20240419.2156` factory image and is
byte-identical to the public LibreELEC copy. The Wi-Fi `.bin` and Rockchip boot
firmware are fetched from exact commits during the build; every payload is
checked by SHA-256. Inspect the resolved source revisions with:

~~~
git -C armbian-build/cache/sources/vontar-dq08-rkbin rev-parse HEAD
git -C \
  armbian-build/cache/sources/vontar-dq08-brcmfmac-sdio-firmware \
  rev-parse HEAD
~~~

Expected commits:

~~~
f43a462e7a1429a9d407ae52b4745033034a6cf9  rockchip-linux/rkbin
5987820e4ff88a5626536f66257165fe3a781b73  LibreELEC/brcmfmac_sdio-firmware
~~~

Verify all selected files:

~~~
sha256sum \
  armbian-build/cache/sources/vontar-dq08-brcmfmac-sdio-firmware/brcmfmac4335-sdio.bin \
  dq08-armbian-bsp/extensions/dq08-bsp/files/usr/lib/firmware/brcm/BCM4335A0.hcd \
  dq08-armbian-bsp/extensions/dq08-bsp/files/usr/lib/firmware/brcm/brcmfmac4335-sdio.txt

sha256sum \
  armbian-build/cache/sources/vontar-dq08-rkbin/bin/rk35/rk3528_ddr_1056MHz_4BIT_PCB_v1.10.bin \
  armbian-build/cache/sources/vontar-dq08-rkbin/bin/rk35/rk3528_bl31_v1.18.elf
~~~

Expected SHA-256 values:

~~~
1551fd7680db31d230c70f55860ca071331a37eeb54c9229307b8fa475f9d6e7  brcmfmac4335-sdio.bin
dbe8e44633ac69027cfb7a7f094681578b18415f7b74fe5b033eb34d140891af  brcmfmac4335-sdio.txt
3e14e7f3c02e19408c5783f845329309e23305ab5f33fb19abfd24a73a84cd8a  BCM4335A0.hcd
f404365dd3929481052548c220aff3e82238bc7a679f13ab52e7e4e9ca1cfeb4  rk3528_ddr_1056MHz_4BIT_PCB_v1.10.bin
3dde96556de969c92784e0f37b50a696bd457200353bbb611a91130b0ef960b9  rk3528_bl31_v1.18.elf
~~~

## Automated stable releases

The free release pipeline watches stable Armbian point tags, builds on a
dedicated OCI A1 ARM64 runner, transfers through a private three-day Object
Storage bucket, and validates and publishes from a GitHub-hosted runner. It
pins the rolling Linux branch to one commit and refuses a new current kernel
series until the DTS is ported and hardware-tested.

Provisioning, GitHub configuration, rollout, security boundaries, immutable
release behavior, and recovery are documented in
[docs/release-pipeline.md](docs/release-pipeline.md).

## Put this module in its own Git repository

From this directory:

~~~
cd dq08-armbian-bsp
git init -b main
git add .
git commit -m "Add Vontar DQ08 Armbian BSP module"
git remote add origin YOUR_GIT_URL
git push -u origin main
~~~

Do not commit an Armbian build checkout, cache, or output image into this
repository. They are deliberately outside this module.

## Use it as a submodule in another repository

A larger project can keep this BSP at third_party/dq08-armbian-bsp:

~~~
git submodule add YOUR_GIT_URL third_party/dq08-armbian-bsp
git commit -m "Add DQ08 Armbian BSP submodule"
~~~

Then install and build it from the parent repository:

~~~
./third_party/dq08-armbian-bsp/install.sh ./build/armbian-build
./third_party/dq08-armbian-bsp/build.sh ./build/armbian-build bookworm
~~~

After another clone, populate the submodule with:

~~~
git submodule update --init --recursive
~~~

## Updating an installed copy

After pulling changes to this module, reinstall it:

~~~
git -C dq08-armbian-bsp pull --ff-only
./dq08-armbian-bsp/install.sh --force ./armbian-build
./dq08-armbian-bsp/verify.sh ./armbian-build
~~~

Review local changes before using --force. The option intentionally replaces
different managed files in userpatches.

When changing anything in extensions/dq08-bsp/files/, increment
dq08_bsp_assets_version in extensions/dq08-bsp/dq08-bsp.sh. Armbian hashes the
extension hook but does not independently hash those payload files; the
version bump invalidates its cached BSP package.

## Moving to another current kernel series

The Linux directory name is versioned intentionally. To port from 6.18 to a
new supported current series:

1. Check Armbian's rockchip64 current kernel series.
2. Copy the kernel directory to kernel/archive/rockchip64-X.Y/.
3. Rebase and compile the DQ08 DTS against that series.
4. Update DQ08_KERNEL_SERIES and DQ08_TESTED_KERNEL in module.conf.
5. Update the kernel path in manifest.txt.
6. Run verify.sh, config-dump, and a complete clean build.
7. Boot-test microSD, Ethernet, eMMC, USB, Wi-Fi, Bluetooth, IR, serial, and
   the front panel before publishing the update.

Do not silently reuse a 6.18 DTS on another series: included RK3528 device-tree
interfaces can change.

## Building a similar BSP module

This repository is also a template for another Armbian board:

1. Add a declarative board file below config/boards/.
2. Put kernel additions below kernel/archive/FAMILY-SERIES/.
3. Put U-Boot patches below u-boot/VERSION/board_NAME/.
4. Put procedural build hooks and root-filesystem payloads in an extension.
5. Enable that extension from the board file.
6. List every installed file and mode in manifest.txt.
7. Pin external boot firmware to exact commits and verify its checksums.
8. Update module.conf, then run verify.sh against a clean Armbian checkout.

Keep board-specific logic in the extension and keep the board file small. This
makes the bundle portable and avoids patching Armbian's own tracked files.

## Uninstall

Preview removal:

~~~
./dq08-armbian-bsp/uninstall.sh --dry-run ./armbian-build
~~~

Remove the module:

~~~
./dq08-armbian-bsp/uninstall.sh ./armbian-build
~~~

The uninstaller removes only identical managed files and preserves unrelated
userpatches. It refuses to delete a locally modified managed file unless
--force is explicitly supplied.

## Provenance and licensing

The hardware information was derived from
[fensoft/dq08-haos](https://github.com/fensoft/dq08-haos) and its rk3528-tvbox
source, then adapted to upstream Linux 6.18 and Armbian's userpatches
interfaces. Source files carry their SPDX license identifiers; retain those
notices when redistributing or modifying them.
