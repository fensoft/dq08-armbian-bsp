# Automated Armbian release pipeline

This repository builds and publishes one DQ08 image for each stable Armbian
point release at or after `v26.5.1`. Weekly trunk and release-candidate tags are
never selected. Releases are software-validated but explicitly set
`hardware_tested: false`; publication is not evidence that the image booted on
a physical Vontar DQ08.

The release name and Git tag are:

```text
dq08-armbian-vX.Y.Z-bsp-vA.B.C
```

`vX.Y.Z` is the exact Armbian tag and `vA.B.C` comes from
`DQ08_MODULE_VERSION` in `module.conf`.

## Trust boundaries

| Stage | Runner | Credentials | Responsibility |
| --- | --- | --- | --- |
| Verify | GitHub-hosted | read-only repository token | Pull-request and push checks, install dry-run, helper tests |
| Control | GitHub-hosted | read-only repository and Actions token | Stable-tag discovery, moved-tag check, Linux-series check, exact kernel resolution |
| State lock | GitHub-hosted | `contents: write` | Persist the exact upstream tag-to-commit mapping before a build |
| Build | OCI A1 self-hosted | Actions artifact read token and bucket-scoped OCI instance principal | Privileged Docker build and private staging upload |
| Publish | GitHub-hosted `release` environment | read-only OCI PAR and ephemeral `contents: write` token | Independent validation and immutable publication |

The privileged builder never receives the OCI read PAR or a GitHub write
token. Pull requests run only on `ubuntu-24.04`; no pull-request event can
select `dq08-builder`.

## One-time setup

### 1. Provision OCI

Follow [`infra/oci/README.md`](../infra/oci/README.md). The OpenTofu stack
creates:

- an Ubuntu 24.04 `VM.Standard.A1.Flex` VM with 2 OCPUs and 12 GB RAM;
- a 50 GB boot disk and protected 100 GB data disk;
- persistent Docker, Actions workspace, and Armbian cache directories;
- a private Object Storage bucket with three-day object expiry;
- bucket-only instance-principal upload permission; and
- a read-only, non-listing pre-authenticated request for the publisher.

The stack never accepts a GitHub token. Register the repository runner
manually with the short-lived token shown by GitHub and give it the custom
label `dq08-builder`. Registration and reprovisioning commands are in the
infrastructure guide.

### 2. Configure GitHub

Create a GitHub Environment named `release`, then store the sensitive OpenTofu
output in that environment:

```bash
cd infra/oci
tofu output -raw staging_par_url |
  gh secret set --env release OCI_STAGING_PAR_URL
```

Set the nonsensitive OCI outputs as repository variables as described in the
infrastructure guide. Keep scheduled publication disabled for rollout by
leaving `DQ08_RELEASE_SCHEDULE_ENABLED` unset or setting it to `false`:

```bash
gh variable set DQ08_RELEASE_SCHEDULE_ENABLED --body false
```

The optional `DQ08_BUILDER_HEALTH_MAX_AGE_MINUTES` variable defaults to `180`.
The controller refuses to queue the privileged job unless the latest hourly
builder-health run completed successfully within that window.

Repository Actions settings must allow the workflow `GITHUB_TOKEN` to request
write permission. Each job then narrows its token: the builder has only
`actions: read`, while state and publication writes stay on hosted runners.
Repository Issues must be enabled for deduplicated failure reporting.
Any branch ruleset covering `automation-state` must allow these workflow-token
commits; the pipeline refuses to build when it cannot lock the upstream tag
mapping first.

### 3. Roll out the baseline

1. Manually run **DQ08 Builder Health** and confirm it succeeds.
2. Run **DQ08 Armbian Release** with `armbian_tag=v26.5.1`, `dry_run=true`, and
   `max_attempts=3`.
3. Inspect the hosted validation result and `build-manifest.json`. A dry run
   writes only the immutable tag mapping; it does not create a GitHub Release.
4. Run the same dispatch with `dry_run=false` to publish the baseline.
5. Enable the hourly builder-health check and release watcher:

   ```bash
   gh variable set DQ08_RELEASE_SCHEDULE_ENABLED --body true
   ```

The watcher runs at minute 17 and processes only the oldest unpublished stable
tag, so missed releases catch up one per run. A manual dispatch with a blank tag
uses the same selection rule. An explicit tag is useful for recovery and
idempotency checks.

## Release policy

Before compilation, the controller:

1. accepts only `vMAJOR.MINOR.PATCH` tags at or after `v26.5.1`;
2. compares every observed tag with `automation/state.json` on the
   `automation-state` branch and refuses a moved or deleted tag;
3. checks out the exact Armbian commit;
4. refuses any `rockchip64/current` series other than the BSP's Linux 6.18
   series, without using `--allow-unsupported`;
5. resolves `linux-6.18.y` once and passes `KERNELBRANCH=commit:<sha>`; and
6. runs module verification, installation verification, and config-dump
   assertions.

The builder compiles the kernel and U-Boot with artifact caches bypassed, then
assembles Bookworm/current/minimal while retaining download, rootfs, and source
caches. It emits `sha,xz` with XZ level 1 and stages one tar object in OCI. The
tar contains exactly:

```text
*.img.xz
*.img.xz.sha
*.img.txt
build-manifest.json
```

The hosted publisher safely extracts that bundle and checks the exact file
count, flat regular-file layout, XZ integrity, SHA-256, image metadata, source
commits, rkbin hashes, maintainer, Bookworm/current/minimal policy, and the
strict `< 2 GiB` per-asset limit.

New releases are created as drafts first. They become public only after all
four asset names and bytes validate. A partial draft can be resumed only when
its target commit and every existing asset match. A final existing release is
never changed: an identical manual rerun is a no-op, while different provenance
or bytes fail and open an issue. No upload uses a clobber option.

Any BSP change intended to produce a new release for an already-published
Armbian tag must also increment `DQ08_MODULE_VERSION`; otherwise immutability
validation correctly reports a conflict.

## Failures and recovery

Source fetches, compilations, and staging uploads retry transient failures up
to the selected attempt count, with three attempts on scheduled runs. The
hosted staging download also uses bounded retries. After failure, the hosted
report job opens or updates one issue for the failure key.

- `kernel-port-required` means Armbian changed the current kernel series. No
  image is published; follow the port and physical-test procedure in
  [`README.full.md`](../README.full.md#moving-to-another-current-kernel-series).
- `runner-offline` means no recent successful health run exists. Reprovision or
  re-register the OCI runner, manually run its health workflow, then dispatch
  the release again.
- An immutable-release conflict requires inspection. The pipeline will not
  replace or delete a published release.
- A failed partial draft can be resumed by dispatching the same Armbian tag;
  differing assets or target commits are refused.

The monthly heartbeat workflow updates `automation/heartbeat.txt` on the
`automation-state` branch so GitHub does not disable the public-repository
schedule after prolonged inactivity. Manual dispatch remains the recovery path.

OCI may reclaim an idle Always Free VM or temporarily have no A1 capacity. The
100 GB cache volume is protected from ordinary destruction; use the
reprovisioning procedure in [`infra/oci/README.md`](../infra/oci/README.md) and
register a fresh short-lived runner token.

## Local checks

These checks do not compile an image:

```bash
./verify.sh
./install.sh --force --dry-run ../armbian-build
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover -s .github/tests -p 'test_*.py' -v
```

When `actionlint` is installed, also run:

```bash
actionlint
```
