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
| U-Boot | v2026.04 |
| Rockchip rkbin | f43a462e7a1429a9d407ae52b4745033034a6cf9 |
| Source BSP | fensoft/dq08-haos at ebc35462a307fad483a7ea0f01b05cbc2b17d458 |

The device tree covers eMMC, microSD, Ethernet, USB, RTL8822CS Wi-Fi/Bluetooth,
infrared input, the power LED, serial console, and the I2C front panel. The
board is deliberately marked headless: upstream Linux 6.18 does not provide
the old vendor multimedia stack used by the legacy BSP, so HDMI, audio, VPU,
and GPU acceleration are outside this module's supported scope.

## Repository layout

~~~
config/boards/
  vontar-dq08.csc              Armbian board definition

extensions/dq08-bsp/
  dq08-bsp.sh                  Armbian build hooks
  files/                       Files copied into the target root filesystem

kernel/archive/rockchip64-6.18/
  dt/rk3528-vontar-dq08.dts    Linux device tree

u-boot/v2026.04/
  board_vontar-dq08/           U-Boot patches

install.sh                     Install into an Armbian checkout
uninstall.sh                   Remove only files managed by this module
build.sh                       Install and build a minimal image
verify.sh                      Check the module and an optional installation
manifest.txt                   Exact list of managed userpatches files
module.conf                    Tested versions and module metadata
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
sha256sum -c *.img.sha
fdisk -l *.img
~~~

If more than one image exists, name the intended image explicitly instead of
using a wildcard.

The module does not commit proprietary firmware binaries. During the build it
fetches this exact public rkbin commit:

~~~
git -C armbian-build/cache/sources/vontar-dq08-rkbin rev-parse HEAD

sha256sum \
  armbian-build/cache/sources/vontar-dq08-rkbin/bin/rk35/rk3528_ddr_1056MHz_4BIT_PCB_v1.10.bin \
  armbian-build/cache/sources/vontar-dq08-rkbin/bin/rk35/rk3528_bl31_v1.18.elf
~~~

Expected SHA-256 values:

~~~
f404365dd3929481052548c220aff3e82238bc7a679f13ab52e7e4e9ca1cfeb4  rk3528_ddr_1056MHz_4BIT_PCB_v1.10.bin
3dde96556de969c92784e0f37b50a696bd457200353bbb611a91130b0ef960b9  rk3528_bl31_v1.18.elf
~~~

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
7. Boot-test microSD, Ethernet, eMMC, USB, Wi-Fi/Bluetooth, IR, serial, and the
   front panel before publishing the update.

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
