resource "oci_core_instance" "builder" {
  availability_domain  = local.availability_domain
  compartment_id       = var.compartment_ocid
  display_name         = "${var.name_prefix}-builder"
  shape                = "VM.Standard.A1.Flex"
  preserve_boot_volume = false
  freeform_tags        = local.common_tags

  shape_config {
    ocpus         = 2
    memory_in_gbs = 12
  }

  source_details {
    source_type             = "image"
    source_id               = local.ubuntu_image_ocid
    boot_volume_size_in_gbs = 50
    boot_volume_vpus_per_gb = 10
  }

  create_vnic_details {
    assign_public_ip          = true
    assign_private_dns_record = true
    display_name              = "${var.name_prefix}-primary-vnic"
    hostname_label            = "dq08-builder"
    subnet_id                 = oci_core_subnet.builder.id
    freeform_tags             = local.common_tags
  }

  instance_options {
    are_legacy_imds_endpoints_disabled = true
  }

  availability_config {
    is_live_migration_preferred = true
    recovery_action             = "RESTORE_INSTANCE"
  }

  is_pv_encryption_in_transit_enabled = true

  metadata = {
    ssh_authorized_keys = trimspace(var.ssh_public_key)
    user_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tftpl", {
      armbian_cache_dir        = local.armbian_cache_dir
      data_volume_device       = local.data_volume_device
      github_repository        = var.github_repository
      object_storage_namespace = data.oci_objectstorage_namespace.this.namespace
      persistent_root          = local.persistent_root
      region                   = var.region
      runner_install_dir       = local.runner_install_dir
      runner_label             = local.runner_label
      runner_user              = local.runner_user
      runner_work_dir          = local.runner_work_dir
      staging_bucket_name      = local.staging_bucket_name
    }))
  }

  lifecycle {
    precondition {
      condition     = var.region == local.tenancy_home_region
      error_message = "region must be the tenancy home region (${local.tenancy_home_region}) so the A1 instance and IAM resources remain Always Free and use the correct identity endpoint."
    }
  }
}

resource "oci_core_volume" "builder_data" {
  availability_domain = local.availability_domain
  compartment_id      = var.compartment_ocid
  display_name        = "${var.name_prefix}-persistent-data"
  size_in_gbs         = 100
  vpus_per_gb         = 10
  freeform_tags       = merge(local.common_tags, { Persistence = "preserve" })

  # The instance is disposable; its build/cache disk is not. See README.md for
  # intentional final teardown and import/recovery procedures.
  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = var.region == local.tenancy_home_region
      error_message = "region must be the tenancy home region (${local.tenancy_home_region}); block volumes outside it incur regular charges."
    }
  }
}

resource "oci_core_volume_attachment" "builder_data" {
  attachment_type                     = "paravirtualized"
  device                              = local.data_volume_device
  display_name                        = "${var.name_prefix}-persistent-data"
  instance_id                         = oci_core_instance.builder.id
  volume_id                           = oci_core_volume.builder_data.id
  is_pv_encryption_in_transit_enabled = true
  is_read_only                        = false
  is_shareable                        = false
}
