# Vontar DQ08 Armbian BSP

Portable Armbian `userpatches` BSP for the Vontar DQ08 (RK3528). It builds a
headless Bookworm image with current Linux 6.18, U-Boot 2026.04, pinned rkbin
DDR/BL31, HK2735M/BCM4335 Wi-Fi/Bluetooth, IR support, and the front-panel
service. The target module enumerates as Broadcom SDIO `02d0:4335`. The build
keeps Armbian's lean firmware package and adds checksum-pinned BCM4335
firmware, NVRAM, and HCD files from a fixed upstream commit.

Full documentation: [README.full.md](README.full.md).

Automated stable-release pipeline: [docs/release-pipeline.md](docs/release-pipeline.md).

## Build

Requires Git, Docker, and the module plus Armbian checkout as sibling
directories. The tested Armbian revision is
`90fda43901b0127104227975ae62d35fbad05abc`.

```sh
git clone https://github.com/armbian/build.git armbian-build
git -C armbian-build checkout --detach 90fda43901b0127104227975ae62d35fbad05abc

./dq08-armbian-bsp/verify.sh
./dq08-armbian-bsp/build.sh ./armbian-build bookworm \
  KERNELBRANCH=commit:f89c296854b755a66657065c35b05406fc18264d \
  COMPRESS_OUTPUTIMAGE=sha,xz \
  IMAGE_XZ_COMPRESSION_RATIO=1
```

`build.sh` installs the BSP into `armbian-build/userpatches/` before building.
The image is written to `armbian-build/output/images/`.

## Runtime gate

The BCM4335 payload is checked inside the image at build time, but the rebuilt
image is not hardware-validated until it passes this test after boot:

```sh
cat /sys/bus/sdio/devices/mmc2:0001:1/{vendor,device,modalias}
journalctl -b -k -o cat --no-pager | grep -Ei 'mmc2|brcmfmac|firmware'
lsmod | grep -E 'brcmfmac|brcmutil|cfg80211'
rfkill unblock wifi
wifi_if="$(iw dev | awk '$1 == "Interface" { print $2; exit }')"
test -n "$wifi_if" && ip link set "$wifi_if" up
iw dev "$wifi_if" scan | grep -E '^BSS|^[[:space:]]+SSID:'
```

Pass requires vendor `0x02d0`, device `0x4335`, a BCM4335 firmware-version
message, and visible scan results. A successful build alone does not establish
that the radio works on hardware.

Install or validate without building:

```sh
./dq08-armbian-bsp/install.sh ./armbian-build
./dq08-armbian-bsp/verify.sh ./armbian-build
```

For a forced kernel/U-Boot rebuild, append:

```sh
ARTIFACT_IGNORE_CACHE=yes CLEAN_LEVEL=make-kernel,make-uboot
```

Official automated releases contain an XZ-compressed image, its checksum and
metadata, and `build-manifest.json`. They are software-validated but explicitly
marked as not tested on physical DQ08 hardware.
