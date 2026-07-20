data "oci_identity_availability_domains" "available" {
  compartment_id = var.tenancy_ocid
}

data "oci_identity_region_subscriptions" "tenancy" {
  tenancy_id = var.tenancy_ocid
}

data "oci_core_images" "ubuntu" {
  count = var.ubuntu_image_ocid == null ? 1 : 0

  compartment_id           = var.compartment_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "24.04"
  shape                    = "VM.Standard.A1.Flex"
  state                    = "AVAILABLE"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

data "oci_objectstorage_namespace" "this" {
  compartment_id = var.tenancy_ocid
}

locals {
  tenancy_home_region = one([
    for subscription in data.oci_identity_region_subscriptions.tenancy.region_subscriptions :
    subscription.region_name if subscription.is_home_region
  ])
  availability_domain = var.availability_domain != null ? var.availability_domain : data.oci_identity_availability_domains.available.availability_domains[0].name
  ubuntu_image_ocid   = var.ubuntu_image_ocid != null ? var.ubuntu_image_ocid : data.oci_core_images.ubuntu[0].images[0].id
  staging_bucket_name = var.staging_bucket_name != null ? var.staging_bucket_name : "${var.name_prefix}-staging"
  iam_scope           = var.compartment_ocid == var.tenancy_ocid ? "in tenancy" : "in compartment id ${var.compartment_ocid}"

  runner_label       = "dq08-builder"
  runner_user        = "github-runner"
  runner_install_dir = "/opt/actions-runner"
  persistent_root    = "/srv/dq08"
  runner_work_dir    = "/srv/dq08/actions/_work"
  armbian_cache_dir  = "/srv/dq08/armbian/cache"
  data_volume_device = "/dev/oracleoci/oraclevdb"

  common_tags = merge(
    {
      Project   = "vontar-dq08-armbian"
      ManagedBy = "opentofu"
      Workload  = "github-actions-builder"
    },
    var.freeform_tags,
  )
}
