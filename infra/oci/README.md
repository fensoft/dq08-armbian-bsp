# OCI Always Free Armbian builder

This OpenTofu stack provisions the ARM64 machine and staging storage used by the
DQ08 release pipeline:

- one `VM.Standard.A1.Flex` Ubuntu 24.04 instance with 2 OCPUs, 12 GB RAM, and a
  50 GB boot volume;
- one protected 100 GB detachable block volume mounted at `/srv/dq08`;
- a dedicated public subnet with SSH restricted to `admin_ssh_cidr` and outbound
  traffic restricted to HTTP(S), DNS, and NTP;
- a private Object Storage bucket whose objects expire after three days;
- the regional Object Storage service permission required to enforce those
  lifecycle rules inside the dedicated DQ08 compartment;
- a bucket-scoped instance principal for multipart uploads; and
- a read-only, non-listing pre-authenticated request (PAR) for the hosted GitHub
  publisher job.

The VM is disposable. Docker data, the runner work directory, and the Armbian
cache live on the detachable volume. The stack deliberately never receives a
GitHub registration token, PAT, deploy key, or other long-lived GitHub secret.

OCI executes lifecycle rules as the regional Object Storage service. The stack
therefore creates Oracle's required root-compartment service policy, scoped to
the dedicated DQ08 compartment. This policy is separate from the narrower
instance-principal policy used by the builder itself.

## Prerequisites

1. An OCI tenancy with Always Free A1 and Block Volume capacity in its home
   region. The default allocation consumes all 2 free A1 OCPUs and 12 GB of
   free A1 memory, plus 150 of 200 GB combined free boot/block storage. The
   stack discovers the tenancy home region and refuses to plan chargeable A1,
   block-volume, or staging resources when `region` differs from it.
   Always Free Object Storage is limited to 20 GB total. Release reruns
   overwrite the same private staging key, and lifecycle policy deletes every
   completed object after three days, but monitor tenancy-wide Object Storage
   usage if processing an unusually large release backlog. See Oracle's
   [current Always Free limits](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).
2. OpenTofu 1.6+ (Terraform 1.6+ is also compatible) and OCI provider
   credentials with permission to manage Compute, Networking, Block Volume,
   Object Storage, dynamic groups, and policies. Creating a dynamic group is a
   tenancy-level operation.
3. A public SSH key and a narrow administrator CIDR, normally `<public-ip>/32`.
4. A public GitHub repository. Free self-hosted runners execute code with the
   permissions of the local runner account, so never route untrusted pull
   requests to `dq08-builder`.

Configure OCI provider authentication using `~/.oci/config`, standard `OCI_*`
environment variables, or OCI Resource Manager. Do not put API private keys in
`terraform.tfvars`.

## Provision

```bash
cd infra/oci
cp terraform.tfvars.example terraform.tfvars
# Edit every required value, set region to the tenancy home region, and choose
# a future PAR expiration.
tofu init
tofu fmt -check
tofu validate
tofu plan -out=dq08.tfplan
tofu apply dq08.tfplan
```

If OCI reports no A1 capacity, change `availability_domain` and retry. If image
discovery returns no image, select the newest Canonical Ubuntu 24.04 aarch64
platform image for `VM.Standard.A1.Flex` in the OCI console and set
`ubuntu_image_ocid`.

Wait for cloud-init and verify the persistent disk before registering a runner:

```bash
ssh ubuntu@"$(tofu output -raw builder_public_ip)"
sudo cloud-init status --wait --long
findmnt /srv/dq08
sudo systemctl --no-pager --full status dq08-data-volume docker
sudo -u github-runner docker info
oci --auth instance_principal os bucket get \
  --namespace-name "$(. /etc/dq08-builder.env; echo "$OCI_OBJECT_STORAGE_NAMESPACE")" \
  --name "$(. /etc/dq08-builder.env; echo "$OCI_STAGING_BUCKET")"
```

IAM changes can take several minutes (and cached instance-principal tokens can
take longer) to become effective. A temporary authorization failure immediately
after `apply` does not justify adding a user API key to the VM.

## Register the repository runner

In GitHub, open **Settings → Actions → Runners → New self-hosted runner**, choose
Linux/ARM64, and use GitHub's current download and checksum commands. Run the
download/extract commands as `github-runner` in `/opt/actions-runner`. Use the
one-hour repository registration token only at the interactive `config.sh` step:

```bash
sudo -iu github-runner
cd /opt/actions-runner
# Run GitHub's displayed, checksum-verified ARM64 download/extract commands.
./config.sh \
  --url "https://github.com/OWNER/REPOSITORY" \
  --token "ONE_HOUR_REGISTRATION_TOKEN" \
  --name "dq08-oci-a1" \
  --labels "dq08-builder" \
  --work "/srv/dq08/actions/_work" \
  --unattended \
  --replace
exit
cd /opt/actions-runner
sudo /usr/local/sbin/dq08-install-runner-service
```

The service helper refuses to run unless `/srv/dq08` is mounted, then installs a
systemd dependency and mount-point condition so the runner cannot start without
the persistent volume. Replace `OWNER/REPOSITORY` with the configured
`github_repository`. Do not save
the registration token in shell profiles, cloud-init, Terraform, or repository
secrets; GitHub exchanges it for the runner's own credentials during setup.
Build jobs should require all labels `[self-hosted, Linux, ARM64, dq08-builder]`.

The runner account is in the `docker` group (effectively root through Docker),
but it has no passwordless `sudo`. Pull requests must remain on GitHub-hosted
runners and must never be able to invoke a workflow using this runner.

## Configure GitHub publication

Set these repository variables from nonsensitive outputs:

```bash
gh variable set OCI_REGION --body "$(tofu output -raw oci_region)"
gh variable set OCI_OBJECT_STORAGE_NAMESPACE \
  --body "$(tofu output -raw object_storage_namespace)"
gh variable set OCI_STAGING_BUCKET \
  --body "$(tofu output -raw staging_bucket_name)"
```

Create or select the GitHub Environment named `release`, then set the full
read-only PAR URL as an environment secret. It is a bearer credential even
though it cannot list, upload, overwrite, or delete objects:

```bash
tofu output -raw staging_par_url | \
  gh secret set --env release OCI_STAGING_PAR_URL
```

The URL is a base ending in `/o/`; the publisher appends the URL-encoded exact
object name. The builder does not use the PAR. It loads `/etc/dq08-builder.env`
and invokes OCI CLI with `--auth instance_principal`. Self-hosted workflow steps
must explicitly run `set -a; source /etc/dq08-builder.env; set +a`; runner jobs
are non-login shells and cannot rely on `/etc/profile.d`. The policy permits the
multipart create/overwrite/inspect/read operations needed by OCI CLI, but no
object deletion and no bucket management. Failed multipart uploads are aborted
by lifecycle policy after one day; completed staging objects are deleted after
three days.

Terraform/OpenTofu state contains the PAR URL. Keep state private and never
commit it. Rotate the PAR before `staging_par_expiration` by changing the value,
applying, and immediately updating `OCI_STAGING_PAR_URL`.

## Disposable compute and recovery

Capture the persistent volume OCID somewhere secure before maintenance:

```bash
tofu output -raw data_volume_id
```

Replace a reclaimed, damaged, or misconfigured VM while retaining all cached
data:

```bash
# For a reachable VM, first drain any active Actions job, then stop all writers
# and power it off cleanly before detaching its data volume.
ssh ubuntu@"$(tofu output -raw builder_public_ip)"
sudo systemctl stop 'actions.runner.*.service' docker.service docker.socket
sudo umount /srv/dq08
sudo shutdown -h now

# Run from the OpenTofu workstation after the instance has stopped.
tofu apply -replace=oci_core_instance.builder
```

This recreates the attachment and updates the exact-instance dynamic-group rule.
Remove the old offline runner record in GitHub, wait for IAM propagation, and
repeat the runner registration steps with a fresh one-hour token. Runner binaries
and configuration are on the disposable boot disk; `_work`, Docker layers, and
Armbian caches remain on `/srv/dq08`.

If Oracle already reclaimed the VM or it is unreachable, a clean unmount is not
possible. Preserve the volume, let ext4 journal recovery run when it is next
attached, and investigate any filesystem errors from a recovery instance; the
provisioning script will never format a volume that already has a signature.

The data volume has `prevent_destroy = true`, so an ordinary full `tofu destroy`
fails rather than erase build caches. To remove disposable compute but retain the
rest of the stack:

```bash
# Perform the same runner/Docker stop, unmount, and shutdown sequence above first.
tofu destroy -target=oci_core_volume_attachment.builder_data
tofu destroy -target=oci_core_instance.builder
```

For a deliberate final teardown, first back up anything needed from `/srv/dq08`,
record the volume OCID, and change `prevent_destroy` to `false` in
`oci_core_volume.builder_data`. Review a full destroy plan before applying it.
Never remove the volume from state and delete it manually unless permanent data
loss is intended.

If state is lost, restore a private state backup first. Do not apply a plan from
empty state while any stack resources still exist: it can create partial
duplicates and then fail on the existing bucket or IAM names. Import every
surviving VCN, subnet, gateway, instance, attachment, volume, bucket, PAR,
dynamic group, policy, and lifecycle policy before planning, or explicitly
retire all disposable resources and retain only the volume.

Only after confirming that the protected volume is the sole surviving stack
resource, restore the configuration and import it before applying:

```bash
tofu import oci_core_volume.builder_data ocid1.volume.oc1.REGION.REPLACE_ME
tofu plan
```

Confirm that the imported volume and the selected availability domain match.
OpenTofu will then attach the existing ext4 filesystem without formatting it.
