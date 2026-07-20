# Vontar DQ08 Armbian BSP

Portable Armbian `userpatches` BSP for the Vontar DQ08 (RK3528). It builds a
headless Bookworm image with current Linux 6.18, U-Boot 2026.04, pinned rkbin
DDR/BL31, IR support, and the front-panel service.

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
