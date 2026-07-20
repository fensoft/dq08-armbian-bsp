output "builder_instance_id" {
  description = "OCID of the disposable A1 builder instance."
  value       = oci_core_instance.builder.id
}

output "builder_public_ip" {
  description = "Ephemeral public IPv4 address of the builder."
  value       = oci_core_instance.builder.public_ip
}

output "builder_ssh_command" {
  description = "SSH command for the Ubuntu platform image's default account."
  value       = "ssh ubuntu@${oci_core_instance.builder.public_ip}"
}

output "builder_image_id" {
  description = "Exact Ubuntu 24.04 aarch64 platform image selected for this deployment."
  value       = local.ubuntu_image_ocid
}

output "data_volume_id" {
  description = "OCID of the protected persistent 100 GB data volume. Save this outside Terraform state for recovery."
  value       = oci_core_volume.builder_data.id
}

output "oci_region" {
  description = "Value for the OCI_REGION GitHub repository variable."
  value       = var.region
}

output "tenancy_home_region" {
  description = "OCI tenancy home region verified by the Always Free guard."
  value       = local.tenancy_home_region
}

output "object_storage_namespace" {
  description = "Value for the OCI_OBJECT_STORAGE_NAMESPACE GitHub repository variable."
  value       = data.oci_objectstorage_namespace.this.namespace
}

output "staging_bucket_name" {
  description = "Value for the OCI_STAGING_BUCKET GitHub repository variable."
  value       = oci_objectstorage_bucket.staging.name
}

output "staging_par_url" {
  description = "Read-only, non-listing PAR base URL for the OCI_STAGING_PAR_URL GitHub secret. Treat it as a bearer secret."
  value       = "https://objectstorage.${var.region}.oraclecloud.com${oci_objectstorage_preauthrequest.publisher_read.access_uri}"
  sensitive   = true
}

output "runner_label" {
  description = "Custom label required by self-hosted build jobs."
  value       = local.runner_label
}

output "runner_user" {
  description = "Unprivileged operating-system account for the GitHub Actions runner service."
  value       = local.runner_user
}

output "runner_install_dir" {
  description = "Runner binary/configuration directory on the boot volume."
  value       = local.runner_install_dir
}

output "runner_work_dir" {
  description = "Persistent GitHub Actions work directory."
  value       = local.runner_work_dir
}

output "armbian_cache_dir" {
  description = "Persistent cache directory to bind into Armbian builds."
  value       = local.armbian_cache_dir
}
